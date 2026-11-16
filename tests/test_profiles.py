import hashlib
from unittest.mock import call, patch

from app.models import (
    Board,
    BoardItem,
    Category,
    Pictogram,
    Profile,
)


def test_delete_profile_removes_related_data_and_storage_objects(
    authenticated_client,
    profile_id,
    board_id,
    db_session,
):
    # Cria uma categoria para os pictogramas.
    category = Category(name="Rotina")
    db_session.add(category)
    db_session.flush()

    # Cria dois pictogramas personalizados do perfil.
    custom_pictograms = [
        Pictogram(
            name="Cachorro",
            image_url=None,
            storage_path=f"{profile_id}/cachorro.webp",
            content_hash=hashlib.sha256(b"cachorro").hexdigest(),
            profile_id=profile_id,
            category_id=category.id,
        ),
        Pictogram(
            name="Gato",
            image_url=None,
            storage_path=f"{profile_id}/gato.webp",
            content_hash=hashlib.sha256(b"gato").hexdigest(),
            profile_id=profile_id,
            category_id=category.id,
        ),
    ]

    # Cria um pictograma institucional.
    institutional_pictogram = Pictogram(
        name="Agua",
        image_url="https://example.com/agua.png",
        storage_path=None,
        content_hash=None,
        profile_id=None,
        category_id=category.id,
    )

    db_session.add_all(
        custom_pictograms + [institutional_pictogram]
    )
    db_session.flush()

    # Adiciona um pictograma personalizado a uma prancha.
    board_item = BoardItem(
        board_id=board_id,
        pictogram_id=custom_pictograms[0].id,
        position=1,
    )

    db_session.add(board_item)
    db_session.commit()

    custom_ids = [
        pictogram.id
        for pictogram in custom_pictograms
    ]

    institutional_id = institutional_pictogram.id
    board_item_id = board_item.id

    storage_paths = [
        pictogram.storage_path
        for pictogram in custom_pictograms
    ]

    # Simula a exclusao das imagens no Supabase.
    with patch(
        "app.routes.profiles.delete_pictogram_image"
    ) as delete_mock:

        response = authenticated_client.delete(
            f"/profiles/{profile_id}"
        )

    # Verifica a resposta da API.
    assert response.status_code == 204

    # Confirma que as duas imagens foram removidas.
    delete_mock.assert_has_calls(
        [call(path) for path in storage_paths],
        any_order=True,
    )
    assert delete_mock.call_count == 2

    # Atualiza os dados da sessao e verifica o banco.
    db_session.expire_all()

    assert db_session.get(Profile, profile_id) is None
    assert db_session.get(Board, board_id) is None
    assert db_session.get(BoardItem, board_item_id) is None

    for pictogram_id in custom_ids:
        assert db_session.get(Pictogram, pictogram_id) is None

    # O pictograma institucional deve continuar existindo.
    assert db_session.get(
        Pictogram,
        institutional_id,
    ) is not None

def test_user_cannot_delete_another_users_profile(
    authenticated_client,
    profile_id,
    db_session,
):
    second_user = {
        "email": "another-profile-owner@example.com",
        "password": "AnotherPassword123!",
    }

    register_response = authenticated_client.post(
        "/auth/register",
        json=second_user,
    )

    assert register_response.status_code == 201

    login_response = authenticated_client.post(
        "/auth/login",
        data={
            "username": second_user["email"],
            "password": second_user["password"],
        },
    )

    assert login_response.status_code == 200

    second_user_token = login_response.json()["access_token"]

    authenticated_client.headers.update({
        "Authorization": f"Bearer {second_user_token}"
    })

    response = authenticated_client.delete(
        f"/profiles/{profile_id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Perfil nao encontrado."

    db_session.expire_all()

    assert db_session.get(Profile, profile_id) is not None

def test_delete_profile_handles_storage_failure(
    authenticated_client,
    profile_id,
    db_session,
    caplog,
):
    category = Category(name="Rotina")
    db_session.add(category)
    db_session.flush()

    pictogram = Pictogram(
        name="Cachorro",
        image_url=None,
        storage_path=f"{profile_id}/cachorro.webp",
        content_hash=hashlib.sha256(b"cachorro").hexdigest(),
        profile_id=profile_id,
        category_id=category.id,
    )

    db_session.add(pictogram)
    db_session.commit()

    storage_path = pictogram.storage_path
    pictogram_id = pictogram.id

    with (
        patch(
            "app.routes.profiles.delete_pictogram_image",
            side_effect=RuntimeError("Storage unavailable"),
        ) as delete_mock,
        caplog.at_level("ERROR", logger="app.routes.profiles"),
    ):
        response = authenticated_client.delete(
            f"/profiles/{profile_id}"
        )

    assert response.status_code == 204

    delete_mock.assert_called_once_with(storage_path)

    db_session.expire_all()

    assert db_session.get(Profile, profile_id) is None
    assert db_session.get(Pictogram, pictogram_id) is None

    assert "Failed to delete profile pictogram from storage" in caplog.text