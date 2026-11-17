import pytest
from pydantic import ValidationError

from app.schemas.pictogram_suggestion import PictogramSuggestionCreate
from app.models import Category, PictogramSuggestion, User


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