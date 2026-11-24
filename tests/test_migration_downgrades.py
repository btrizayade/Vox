"""PostgreSQL integration tests for data-dependent migration downgrades.

Set MIGRATION_TEST_ADMIN_URL to a local, disposable PostgreSQL 16 database
named ``vox_migration_test_admin``. Each test creates and drops its own
``vox_migration_test_*`` database. These tests never use the project DATABASE_URL.
"""

import hashlib
import io
import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import psycopg2
from psycopg2 import sql
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.database.connection import get_db
from app.dependencies import get_current_user
from app.main import app
from app.models import Category, Pictogram, Profile, User


ADMIN_URL_ENV = "MIGRATION_TEST_ADMIN_URL"
ADMIN_DATABASE = "vox_migration_test_admin"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
HASH_CHECK_NAME = "ck_pictograms_image_source_by_owner"
HASH_UNIQUE_NAME = "uq_pictograms_profile_content_hash"


@pytest.fixture
def migration_database(monkeypatch):
    """Create an isolated database on an explicitly local test server."""
    admin_url_value = os.environ.get(ADMIN_URL_ENV)
    if not admin_url_value:
        pytest.skip(f"{ADMIN_URL_ENV} is not configured")

    admin_url = make_url(admin_url_value)
    if admin_url.host not in LOCAL_HOSTS:
        pytest.fail("Migration integration tests require a loopback PostgreSQL host")
    if admin_url.database != ADMIN_DATABASE:
        pytest.fail(
            f"Migration integration tests require database {ADMIN_DATABASE!r}"
        )

    database_name = f"vox_migration_test_{uuid.uuid4().hex}"
    admin_connection = psycopg2.connect(admin_url.set(drivername="postgresql").render_as_string(hide_password=False))
    admin_connection.autocommit = True

    try:
        with admin_connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(database_name)
                )
            )
    finally:
        admin_connection.close()

    database_url = admin_url.set(database=database_name)
    monkeypatch.setenv("DATABASE_URL", database_url.render_as_string(hide_password=False))

    try:
        yield database_url.render_as_string(hide_password=False)
    finally:
        admin_connection = psycopg2.connect(
            admin_url.set(drivername="postgresql").render_as_string(hide_password=False)
        )
        admin_connection.autocommit = True
        try:
            with admin_connection.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP DATABASE {}").format(
                        sql.Identifier(database_name)
                    )
                )
        finally:
            admin_connection.close()


@pytest.fixture
def migration_database_pair():
    """Create two isolated local databases for upgrade-path comparison."""
    admin_url_value = os.environ.get(ADMIN_URL_ENV)
    if not admin_url_value:
        pytest.skip(f"{ADMIN_URL_ENV} is not configured")

    admin_url = make_url(admin_url_value)
    if admin_url.host not in LOCAL_HOSTS or admin_url.database != ADMIN_DATABASE:
        pytest.fail(
            "Migration integration tests require the local "
            f"{ADMIN_DATABASE!r} database"
        )

    database_names = [
        f"vox_migration_test_{uuid.uuid4().hex}"
        for _ in range(2)
    ]
    admin_connection = psycopg2.connect(
        admin_url.set(drivername="postgresql").render_as_string(
            hide_password=False
        )
    )
    admin_connection.autocommit = True
    try:
        with admin_connection.cursor() as cursor:
            for database_name in database_names:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(database_name)
                    )
                )
    finally:
        admin_connection.close()

    database_urls = [
        admin_url.set(database=database_name).render_as_string(
            hide_password=False
        )
        for database_name in database_names
    ]
    try:
        yield database_urls
    finally:
        admin_connection = psycopg2.connect(
            admin_url.set(drivername="postgresql").render_as_string(
                hide_password=False
            )
        )
        admin_connection.autocommit = True
        try:
            with admin_connection.cursor() as cursor:
                for database_name in database_names:
                    cursor.execute(
                        sql.SQL("DROP DATABASE {}").format(
                            sql.Identifier(database_name)
                        )
                    )
        finally:
            admin_connection.close()


def run_migration(database_url: str, action: str, revision: str) -> None:
    """Run Alembic with an explicit disposable database URL."""
    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", action, revision],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def current_revision(database_url: str) -> str:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
    finally:
        engine.dispose()


def insert_owner_and_category(connection, email: str) -> tuple[int, int]:
    user_id = connection.execute(
        text(
            "INSERT INTO users (email, password_hash, created_at) "
            "VALUES (:email, 'unused', CURRENT_TIMESTAMP) RETURNING id"
        ),
        {"email": email},
    ).scalar_one()
    profile_id = connection.execute(
        text(
            "INSERT INTO profiles "
            "(user_id, name, created_at, updated_at) "
            "VALUES (:user_id, 'Test profile', CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP) RETURNING id"
        ),
        {"user_id": user_id},
    ).scalar_one()
    category_id = connection.execute(
        text(
            "INSERT INTO categories (name, created_at) "
            "VALUES (:name, CURRENT_TIMESTAMP) RETURNING id"
        ),
        {"name": f"category-{email}"},
    ).scalar_one()
    return profile_id, category_id


def constraint_snapshot(database_url: str) -> tuple:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return tuple(
                connection.execute(
                    text(
                        "SELECT conname, contype, pg_get_constraintdef(oid), "
                        "convalidated FROM pg_constraint "
                        "WHERE conrelid = 'pictograms'::regclass "
                        "AND conname IN (:check_name, :unique_name) "
                        "ORDER BY conname"
                    ),
                    {
                        "check_name": HASH_CHECK_NAME,
                        "unique_name": HASH_UNIQUE_NAME,
                    },
                ).all()
            )
    finally:
        engine.dispose()


def test_board_downgrade_is_blocked_without_schema_or_data_changes(
    migration_database,
):
    database_url = migration_database
    run_migration(database_url, "upgrade", "8c4792f142da")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO boards "
                    "(profile_id, name, board_type, created_at, updated_at) "
                    "VALUES (NULL, 'System board', 'system', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match=r"1 system board\(s\) exist"):
        run_migration(database_url, "downgrade", "eba707ff61e5")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        assert {"board_type", "profile_id"}.issubset(
            {column["name"] for column in inspector.get_columns("boards")}
        )
        board_columns = {
            column["name"]: column
            for column in inspector.get_columns("boards")
        }
        assert board_columns["profile_id"]["nullable"] is True
        assert board_columns["board_type"]["nullable"] is False
        assert {"ck_boards_board_type", "ck_boards_profile_by_type"}.issubset(
            {constraint["name"] for constraint in inspector.get_check_constraints("boards")}
        )
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT profile_id, name, board_type FROM boards")
            ).one()
            assert row == (None, "System board", "system")
    finally:
        engine.dispose()
    assert current_revision(database_url) == "8c4792f142da"


def test_board_downgrade_succeeds_without_system_boards(migration_database):
    database_url = migration_database
    run_migration(database_url, "upgrade", "8c4792f142da")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('custom-board@example.invalid', 'unused', CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO profiles "
                    "(user_id, name, created_at, updated_at) "
                    "VALUES (1, 'Custom board profile', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO boards "
                    "(profile_id, name, board_type, created_at, updated_at) "
                    "VALUES (1, 'Custom board', 'custom', "
                    "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
    finally:
        engine.dispose()

    run_migration(database_url, "downgrade", "eba707ff61e5")

    engine = create_engine(database_url)
    try:
        columns = {column["name"]: column for column in inspect(engine).get_columns("boards")}
        assert "board_type" not in columns
        assert columns["profile_id"]["nullable"] is False
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT profile_id, name FROM boards")
            ).one()
            assert row == (1, "Custom board")
    finally:
        engine.dispose()
    assert current_revision(database_url) == "eba707ff61e5"


def test_custom_pictogram_downgrade_is_blocked_without_schema_or_data_changes(
    migration_database,
):
    database_url = migration_database
    run_migration(database_url, "upgrade", "e45c6f16bab5")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (email, password_hash, created_at) "
                    "VALUES ('migration-test@example.invalid', 'unused', CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO profiles "
                    "(user_id, name, created_at, updated_at) "
                    "VALUES (1, 'Test profile', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO categories (name, created_at) "
                    "VALUES ('Migration test', CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO pictograms "
                    "(name, image_url, storage_path, profile_id, category_id, created_at) "
                    "VALUES ('Custom test', NULL, '1/test.webp', 1, 1, CURRENT_TIMESTAMP)"
                )
            )
    finally:
        engine.dispose()

    with pytest.raises(RuntimeError, match=r"1 custom pictogram\(s\) exist"):
        run_migration(database_url, "downgrade", "cbb0c07fc6d6")

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        columns = {column["name"]: column for column in inspector.get_columns("pictograms")}
        assert {"profile_id", "storage_path"}.issubset(columns)
        assert columns["image_url"]["nullable"] is True
        assert "ck_pictograms_image_source_by_owner" in {
            constraint["name"]
            for constraint in inspector.get_check_constraints("pictograms")
        }
        assert "fk_pictograms_profile_id_profiles" in {
            constraint["name"]
            for constraint in inspector.get_foreign_keys("pictograms")
        }
        assert "ix_pictograms_profile_id" in {
            index["name"] for index in inspector.get_indexes("pictograms")
        }
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT name, image_url, storage_path, profile_id "
                    "FROM pictograms"
                )
            ).one()
            assert row == ("Custom test", None, "1/test.webp", 1)
    finally:
        engine.dispose()
    assert current_revision(database_url) == "e45c6f16bab5"


def test_pictogram_downgrade_succeeds_without_custom_pictograms(
    migration_database,
):
    database_url = migration_database
    run_migration(database_url, "upgrade", "e45c6f16bab5")

    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO categories (name, created_at) "
                    "VALUES ('Institutional test', CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO pictograms "
                    "(name, image_url, category_id, created_at) "
                    "VALUES ('Institutional test', "
                    "'https://example.invalid/image.png', 1, CURRENT_TIMESTAMP)"
                )
            )
    finally:
        engine.dispose()

    run_migration(database_url, "downgrade", "cbb0c07fc6d6")

    engine = create_engine(database_url)
    try:
        columns = {
            column["name"]: column
            for column in inspect(engine).get_columns("pictograms")
        }
        assert "profile_id" not in columns
        assert "storage_path" not in columns
        assert columns["image_url"]["nullable"] is False
        with engine.connect() as connection:
            row = connection.execute(
                text("SELECT name, image_url FROM pictograms")
            ).one()
            assert row == (
                "Institutional test",
                "https://example.invalid/image.png",
            )
    finally:
        engine.dispose()
    assert current_revision(database_url) == "cbb0c07fc6d6"


def test_legacy_and_former_head_upgrades_converge_without_data_changes(
    migration_database_pair,
):
    legacy_database_url, former_head_database_url = migration_database_pair

    # Path A: e45 contains custom pictograms with no content_hash column.
    run_migration(legacy_database_url, "upgrade", "e45c6f16bab5")
    legacy_engine = create_engine(legacy_database_url)
    try:
        with legacy_engine.begin() as connection:
            profile_id, category_id = insert_owner_and_category(
                connection,
                "legacy-path@example.invalid",
            )
            connection.execute(
                text(
                    "INSERT INTO pictograms "
                    "(name, image_url, storage_path, profile_id, category_id, created_at) "
                    "VALUES ('Legacy custom', NULL, 'legacy/custom.webp', "
                    ":profile_id, :category_id, CURRENT_TIMESTAMP)"
                ),
                {"profile_id": profile_id, "category_id": category_id},
            )
            connection.execute(
                text(
                    "INSERT INTO pictograms "
                    "(name, image_url, storage_path, profile_id, category_id, created_at) "
                    "VALUES ('Institutional', 'https://example.invalid/i.png', "
                    "NULL, NULL, :category_id, CURRENT_TIMESTAMP)"
                ),
                {"category_id": category_id},
            )
    finally:
        legacy_engine.dispose()

    run_migration(legacy_database_url, "upgrade", "head")

    legacy_engine = create_engine(legacy_database_url)
    try:
        with legacy_engine.connect() as connection:
            legacy_rows = connection.execute(
                text(
                    "SELECT name, image_url, storage_path, profile_id, "
                    "content_hash FROM pictograms ORDER BY name"
                )
            ).all()
        assert legacy_rows[0][0] == "Institutional"
        assert legacy_rows[0][1:] == (
            "https://example.invalid/i.png",
            None,
            None,
            None,
        )
        assert legacy_rows[1][0] == "Legacy custom"
        assert legacy_rows[1][1:] == (None, "legacy/custom.webp", 1, None)
    finally:
        legacy_engine.dispose()

    # Path B: simulate the former head schema with its validated strict check.
    run_migration(former_head_database_url, "upgrade", "3c85661c8030")
    old_head_hash = hashlib.sha256(b"old-head-original-upload").hexdigest()
    old_head_engine = create_engine(former_head_database_url)
    try:
        with old_head_engine.begin() as connection:
            profile_id, category_id = insert_owner_and_category(
                connection,
                "former-head@example.invalid",
            )
            connection.execute(
                text(
                    "INSERT INTO pictograms "
                    "(name, image_url, storage_path, profile_id, category_id, "
                    "content_hash, created_at) "
                    "VALUES ('Former head custom', NULL, 'head/custom.webp', "
                    ":profile_id, :category_id, :content_hash, CURRENT_TIMESTAMP)"
                ),
                {
                    "profile_id": profile_id,
                    "category_id": category_id,
                    "content_hash": old_head_hash,
                },
            )
            connection.execute(
                text(
                    "ALTER TABLE pictograms DROP CONSTRAINT "
                    "ck_pictograms_image_source_by_owner"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE pictograms ADD CONSTRAINT "
                    "ck_pictograms_image_source_by_owner CHECK "
                    "((profile_id IS NULL AND image_url IS NOT NULL "
                    "AND storage_path IS NULL AND content_hash IS NULL) OR "
                    "(profile_id IS NOT NULL AND image_url IS NULL "
                    "AND storage_path IS NOT NULL AND content_hash IS NOT NULL))"
                )
            )
    finally:
        old_head_engine.dispose()

    run_migration(former_head_database_url, "upgrade", "head")

    old_head_engine = create_engine(former_head_database_url)
    try:
        with old_head_engine.connect() as connection:
            old_head_rows = connection.execute(
                text(
                    "SELECT name, image_url, storage_path, profile_id, "
                    "content_hash FROM pictograms ORDER BY name"
                )
            ).all()
        assert old_head_rows == [
            (
                "Former head custom",
                None,
                "head/custom.webp",
                1,
                old_head_hash,
            )
        ]
    finally:
        old_head_engine.dispose()

    assert constraint_snapshot(legacy_database_url) == constraint_snapshot(
        former_head_database_url
    )
    assert current_revision(legacy_database_url) == "49c7a4d210ef"
    assert current_revision(former_head_database_url) == "49c7a4d210ef"

    # The corrective revision downgrades to the now-permissive 3c schema.
    converged_constraints = constraint_snapshot(legacy_database_url)
    run_migration(legacy_database_url, "downgrade", "3c85661c8030")
    assert constraint_snapshot(legacy_database_url) == converged_constraints
    assert current_revision(legacy_database_url) == "3c85661c8030"
    legacy_engine = create_engine(legacy_database_url)
    try:
        with legacy_engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT count(*) FROM pictograms "
                    "WHERE name = 'Legacy custom' AND content_hash IS NULL"
                )
            ).scalar_one() == 1
    finally:
        legacy_engine.dispose()


def test_hash_constraints_allow_legacy_nulls_and_preserve_uniqueness(
    migration_database,
):
    database_url = migration_database
    run_migration(database_url, "upgrade", "head")
    engine = create_engine(database_url)
    repeated_hash = hashlib.sha256(b"same-original-file").hexdigest()
    try:
        with engine.begin() as connection:
            profile_one, category_id = insert_owner_and_category(
                connection,
                "hash-owner-one@example.invalid",
            )
            profile_two, _ = insert_owner_and_category(
                connection,
                "hash-owner-two@example.invalid",
            )

            def insert_pictogram(
                *,
                name,
                profile_id,
                image_url,
                storage_path,
                content_hash,
            ):
                connection.execute(
                    text(
                        "INSERT INTO pictograms "
                        "(name, image_url, storage_path, profile_id, "
                        "category_id, content_hash, created_at) "
                        "VALUES (:name, :image_url, :storage_path, :profile_id, "
                        ":category_id, :content_hash, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "name": name,
                        "image_url": image_url,
                        "storage_path": storage_path,
                        "profile_id": profile_id,
                        "category_id": category_id,
                        "content_hash": content_hash,
                    },
                )

            # Institutional rows require URL and forbid owner, storage, and hash.
            insert_pictogram(
                name="Institutional",
                profile_id=None,
                image_url="https://example.invalid/institutional.png",
                storage_path=None,
                content_hash=None,
            )

            # Multiple pre-hash custom records can remain NULL in one profile.
            for name in ("Legacy custom one", "Legacy custom two"):
                insert_pictogram(
                    name=name,
                    profile_id=profile_one,
                    image_url=None,
                    storage_path=f"legacy/{name.replace(' ', '-').lower()}.webp",
                    content_hash=None,
                )

            # A non-null hash is unique per profile, not globally.
            insert_pictogram(
                name="Hashed owner one",
                profile_id=profile_one,
                image_url=None,
                storage_path="hash/owner-one.webp",
                content_hash=repeated_hash,
            )
            insert_pictogram(
                name="Same hash owner two",
                profile_id=profile_two,
                image_url=None,
                storage_path="hash/owner-two.webp",
                content_hash=repeated_hash,
            )

            with pytest.raises(IntegrityError) as duplicate_error:
                with connection.begin_nested():
                    insert_pictogram(
                        name="Duplicate same profile",
                        profile_id=profile_one,
                        image_url=None,
                        storage_path="hash/duplicate.webp",
                        content_hash=repeated_hash,
                    )
            assert duplicate_error.value.orig.diag.constraint_name == HASH_UNIQUE_NAME

            with pytest.raises(IntegrityError) as source_error:
                with connection.begin_nested():
                    insert_pictogram(
                        name="Invalid institutional source",
                        profile_id=None,
                        image_url="https://example.invalid/invalid.png",
                        storage_path="invalid.webp",
                        content_hash=None,
                    )
            assert source_error.value.orig.diag.constraint_name == HASH_CHECK_NAME

            with pytest.raises(IntegrityError) as custom_source_error:
                with connection.begin_nested():
                    insert_pictogram(
                        name="Invalid custom source",
                        profile_id=profile_one,
                        image_url="https://example.invalid/invalid.png",
                        storage_path="invalid-custom.webp",
                        content_hash=repeated_hash,
                    )
            assert custom_source_error.value.orig.diag.constraint_name == HASH_CHECK_NAME
    finally:
        engine.dispose()


def test_custom_pictogram_endpoint_stores_sha256_in_postgresql(
    migration_database,
):
    database_url = migration_database
    run_migration(database_url, "upgrade", "head")
    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with session_factory() as session:
            user = User(
                email="endpoint-hash@example.invalid",
                password_hash="unused",
            )
            session.add(user)
            session.flush()
            profile = Profile(name="Endpoint hash profile", user_id=user.id)
            category = Category(name="Endpoint hash category")
            session.add_all([profile, category])
            session.commit()
            profile_id = profile.id
            user_id = user.id
            category_id = category.id

        def override_get_db():
            with session_factory() as session:
                yield session

        previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=user_id
        )

        image = Image.new("RGB", (48, 48), "purple")
        output = io.BytesIO()
        image.save(output, format="PNG")
        original_bytes = output.getvalue()
        expected_hash = hashlib.sha256(original_bytes).hexdigest()

        try:
            with (
                patch("app.routes.custom_pictograms.upload_pictogram_image") as upload_mock,
                patch(
                    "app.routes.custom_pictograms.create_pictogram_signed_url",
                    return_value="https://example.invalid/signed.webp",
                ),
                TestClient(app) as client,
            ):
                response = client.post(
                    f"/profiles/{profile_id}/pictograms",
                    data={
                        "name": "Endpoint hash pictogram",
                        "category_id": str(category_id),
                    },
                    files={
                        "image": (
                            "original.png",
                            original_bytes,
                            "image/png",
                        )
                    },
                )
            assert response.status_code == 201, response.text
            upload_mock.assert_called_once()

            with session_factory() as session:
                saved_pictogram = (
                    session.query(Pictogram)
                    .filter(Pictogram.profile_id == profile_id)
                    .one()
                )
                assert saved_pictogram.content_hash == expected_hash
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(previous_overrides)
    finally:
        engine.dispose()
