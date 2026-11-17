import pytest
from pydantic import ValidationError

from app.schemas.pictogram_suggestion import PictogramSuggestionCreate
from app.models import Category, PictogramSuggestion, User
from datetime import datetime, timedelta, timezone


def test_create_suggestion_with_existing_category():
    suggestion = PictogramSuggestionCreate(
        name="Garrafa de agua",
        category_id=1,
        description="Um pictograma de uma garrafa de agua.",
    )

    assert suggestion.name == "Garrafa de agua"
    assert suggestion.category_id == 1
    assert suggestion.other_category is None


def test_create_suggestion_with_other_category():
    suggestion = PictogramSuggestionCreate(
        name="Instrumento musical",
        other_category="Musica",
        description="Um pictograma de um instrumento musical.",
    )

    assert suggestion.category_id is None
    assert suggestion.other_category == "Musica"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "Agua",
            "description": "Descricao.",
        },
        {
            "name": "Agua",
            "category_id": 1,
            "other_category": "Outra",
            "description": "Descricao.",
        },
    ],
)
def test_create_suggestion_requires_exactly_one_category(payload):
    with pytest.raises(ValidationError):
        PictogramSuggestionCreate(**payload)


@pytest.mark.parametrize(
    "field",
    ["name", "description"],
)
def test_create_suggestion_rejects_blank_required_text(field):
    payload = {
        "name": "Agua",
        "category_id": 1,
        "description": "Descricao.",
    }

    payload[field] = "   "

    with pytest.raises(ValidationError):
        PictogramSuggestionCreate(**payload)


def test_create_suggestion_strips_text_fields():
    suggestion = PictogramSuggestionCreate(
        name="  Agua  ",
        category_id=1,
        description="  Um pictograma de agua.  ",
        usage_context="  Durante as refeicoes.  ",
    )

    assert suggestion.name == "Agua"
    assert suggestion.description == "Um pictograma de agua."
    assert suggestion.usage_context == "Durante as refeicoes."


def test_create_suggestion_converts_blank_optional_fields_to_none():
    suggestion = PictogramSuggestionCreate(
        name="Agua",
        category_id=1,
        description="Uma representacao de agua.",
        usage_context="   ",
    )

    assert suggestion.usage_context is None

def test_create_suggestion_endpoint(authenticated_client, db_session):
    category = Category(name="Alimentacao")
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)

    response = authenticated_client.post(
        "/pictogram-suggestions/",
        json={
            "name": "Garrafa de agua",
            "category_id": category.id,
            "description": "Uma garrafa de agua.",
            "status": "approved",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["name"] == "Garrafa de agua"
    assert data["category_id"] == category.id
    assert data["status"] == "pending"
    assert "user_id" not in data


def test_create_suggestion_with_other_category_endpoint(
    authenticated_client,
):
    response = authenticated_client.post(
        "/pictogram-suggestions/",
        json={
            "name": "Instrumento musical",
            "other_category": "Musica",
            "description": "Representacao de um instrumento.",
        },
    )

    assert response.status_code == 201
    assert response.json()["other_category"] == "Musica"


def test_create_suggestion_with_invalid_category(
    authenticated_client,
):
    response = authenticated_client.post(
        "/pictogram-suggestions/",
        json={
            "name": "Agua",
            "category_id": 999,
            "description": "Representacao de agua.",
        },
    )

    assert response.status_code == 404


def test_list_suggestions_only_returns_own_suggestions(
    authenticated_client,
    db_session,
):
    other_user = User(
        email="other@example.com",
        password_hash="unused",
    )

    db_session.add(other_user)
    db_session.flush()

    other_suggestion = PictogramSuggestion(
        user_id=other_user.id,
        name="Pictograma de teste",
        other_category="Outra",
        description="Sugestao de outro usuario.",
    )

    db_session.add(other_suggestion)
    db_session.commit()

    response = authenticated_client.post(
        "/pictogram-suggestions/",
        json={
            "name": "Minha sugestao",
            "other_category": "Outra",
            "description": "Minha descricao.",
        },
    )

    assert response.status_code == 201

    own_id = response.json()["id"]

    list_response = authenticated_client.get(
        "/pictogram-suggestions/"
    )

    assert list_response.status_code == 200

    suggestions = list_response.json()

    assert len(suggestions) == 1
    assert suggestions[0]["id"] == own_id


def test_user_cannot_access_another_users_suggestion(
    authenticated_client,
    db_session,
):
    other_user = User(
        email="another@example.com",
        password_hash="unused",
    )

    db_session.add(other_user)
    db_session.flush()

    suggestion = PictogramSuggestion(
        user_id=other_user.id,
        name="Sugestao privada",
        other_category="Outra",
        description="Descricao privada.",
    )

    db_session.add(suggestion)
    db_session.commit()
    db_session.refresh(suggestion)

    response = authenticated_client.get(
        f"/pictogram-suggestions/{suggestion.id}"
    )

    assert response.status_code == 404


def test_list_suggestions_requires_authentication(client):
    response = client.get("/pictogram-suggestions/")

    assert response.status_code == 401

@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "A" * 51),
        ("description", "A" * 501),
        ("usage_context", "A" * 501),
    ],
)
def test_suggestion_rejects_text_over_limit(field, value):
    payload = {
        "name": "Agua",
        "category_id": 1,
        "description": "Representacao de agua.",
        "usage_context": "Durante as refeicoes.",
    }

    payload[field] = value

    with pytest.raises(ValidationError):
        PictogramSuggestionCreate(**payload)


def test_suggestion_accepts_maximum_text_lengths():
    suggestion = PictogramSuggestionCreate(
        name="A" * 50,
        category_id=1,
        description="D" * 500,
        usage_context="C" * 500,
    )

    assert len(suggestion.name) == 50
    assert len(suggestion.description) == 500
    assert len(suggestion.usage_context) == 500

def test_suggestion_hourly_limit(
    authenticated_client,
    db_session,
):
    user = (
        db_session.query(User)
        .filter(User.email == "owner@example.com")
        .first()
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    previous_suggestion = PictogramSuggestion(
        user_id=user.id,
        name="Sugestao anterior",
        other_category="Outra",
        description="Descricao anterior.",
        created_at=now - timedelta(minutes=30),
    )

    db_session.add(previous_suggestion)
    db_session.commit()

    response = authenticated_client.post(
        "/pictogram-suggestions/",
        json={
            "name": "Nova sugestao",
            "other_category": "Outra",
            "description": "Descricao da nova sugestao.",
        },
    )

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0

def test_suggestion_monthly_limit(
    authenticated_client,
    db_session,
):
    user = (
        db_session.query(User)
        .filter(User.email == "owner@example.com")
        .first()
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    month_start = datetime(now.year, now.month, 1)

    suggestions = [
        PictogramSuggestion(
            user_id=user.id,
            name=f"Sugestao {i}",
            other_category="Outra",
            description="Descricao de teste.",
            created_at=month_start + timedelta(seconds=i),
        )
        for i in range(3)
    ]

    db_session.add_all(suggestions)
    db_session.commit()

    response = authenticated_client.post(
        "/pictogram-suggestions/",
        json={
            "name": "Quarta sugestao",
            "other_category": "Outra",
            "description": "Descricao da quarta sugestao.",
        },
    )

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0