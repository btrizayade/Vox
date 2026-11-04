
import os

# Configuracoes exclusivas para os testes.
os.environ["SECRET_KEY"] = "vox-test-secret-key-2026-automated-tests-only"
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.connection import get_db
from app.main import app
from app.models import Board, BoardItem, Category, Pictogram, Profile, User


@pytest.fixture
def testing_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)

    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    try:
        yield TestingSessionLocal
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def db_session(testing_session_factory):
    db = testing_session_factory()

    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(testing_session_factory):
    def override_get_db():
        db = testing_session_factory()

        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client):
    credentials = {
        "email": "owner@example.com",
        "password": "TestPassword123!",
    }

    register_response = client.post(
        "/auth/register",
        json=credentials,
    )

    assert register_response.status_code == 201, register_response.text

    login_response = client.post(
        "/auth/login",
        data={
            "username": credentials["email"],
            "password": credentials["password"],
        },
    )

    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]

    client.headers.update({
        "Authorization": f"Bearer {token}"
    })

    return client


@pytest.fixture
def profile_id(authenticated_client):
    response = authenticated_client.post(
        "/profiles/",
        json={"name": "Perfil de teste"},
    )

    assert response.status_code == 201, response.text

    return response.json()["id"]


@pytest.fixture
def board_id(authenticated_client, profile_id):
    response = authenticated_client.post(
        "/boards/",
        json={
            "profile_id": profile_id,
            "name": "Rotina diaria",
        },
    )

    assert response.status_code == 201, response.text

    return response.json()["id"]

@pytest.fixture
def system_board_id(db_session):
    board = Board(
        profile_id=None,
        name="Escola",
        board_type="system",
    )

    db_session.add(board)
    db_session.commit()
    db_session.refresh(board)

    return board.id

@pytest.fixture
def pictogram_ids(db_session):
    category = Category(name="Alimentacao")

    db_session.add(category)
    db_session.flush()

    pictograms = [
        Pictogram(
            name="Agua",
            image_url="https://example.com/agua.png",
            category_id=category.id,
        ),
        Pictogram(
            name="Comida",
            image_url="https://example.com/comida.png",
            category_id=category.id,
        ),
        Pictogram(
            name="Fruta",
            image_url="https://example.com/fruta.png",
            category_id=category.id,
        ),
    ]

    db_session.add_all(pictograms)
    db_session.commit()

    for pictogram in pictograms:
        db_session.refresh(pictogram)

    return [pictogram.id for pictogram in pictograms]
