import os

# Configuracoes exclusivas para os testes.
# Evita depender do .env ou do Supabase.
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
from app.models import Board, Category, Pictogram, Profile, User


@pytest.fixture
def client():
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

    def override_get_db():
        db = TestingSessionLocal()

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
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

@pytest.fixture
def authenticated_client(client):
    credentials = {
        "email": "owner@example.com",
        "password": "TestPassword123!",
    }

    # Cria um usuario para o teste
    register_response = client.post(
        "/auth/register",
        json=credentials,
    )

    assert register_response.status_code == 201, register_response.text

    # Faz login e obtem o JWT
    login_response = client.post(
        "/auth/login",
        data={
            "username": credentials["email"],
            "password": credentials["password"],
        },
    )

    assert login_response.status_code == 200, login_response.text

    token = login_response.json()["access_token"]

    # Adiciona o token as requisicoes seguintes
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

