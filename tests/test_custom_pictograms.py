import hashlib
import io
from unittest.mock import patch

import pytest
from PIL import Image

from app.models import Category, Pictogram

def test_create_custom_pictogram_rejects_blank_name(
    authenticated_client,
    profile_id,
):
    response = authenticated_client.post(
        f"/profiles/{profile_id}/pictograms",
        data={
            "name": "   ",
            "category_id": "1",
        },
        files={
            "image": ("image.png", b"fake-image", "image/png"),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "O nome do pictograma nao pode estar vazio."
    )


def test_create_custom_pictogram_rejects_nonexistent_profile(
    authenticated_client,
):
    response = authenticated_client.post(
        "/profiles/9999/pictograms",
        data={
            "name": "Cachorro",
            "category_id": "1",
        },
        files={
            "image": ("image.png", b"fake-image", "image/png"),
        },
    )

    assert response.status_code == 404


def test_create_custom_pictogram_rejects_nonexistent_category(
    authenticated_client,
    profile_id,
):
    response = authenticated_client.post(
        f"/profiles/{profile_id}/pictograms",
        data={
            "name": "Cachorro",
            "category_id": "9999",
        },
        files={
            "image": ("image.png", b"fake-image", "image/png"),
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Categoria nao encontrada."

@pytest.fixture
def category_id(db_session):
    category = Category(name="Rotina")

    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)

    return category.id


@pytest.fixture
def valid_png():
    image = Image.new("RGB", (100, 100), "red")

    output = io.BytesIO()
    image.save(output, format="PNG")

    return output.getvalue()

def test_create_custom_pictogram_success(
    authenticated_client,
    profile_id,
    category_id,
    valid_png,
    db_session,
):
    with (
        patch(
            "app.routes.custom_pictograms.upload_pictogram_image"
        ) as upload_mock,
        patch(
            "app.routes.custom_pictograms.create_pictogram_signed_url",
            return_value="https://example.com/signed-image.webp",
        ),
    ):
        response = authenticated_client.post(
            f"/profiles/{profile_id}/pictograms",
            data={
                "name": "Cachorro",
                "category_id": str(category_id),
            },
            files={
                "image": ("cachorro.png", valid_png, "image/png"),
            },
        )

    assert response.status_code == 201

    response_data = response.json()

    assert response_data["name"] == "Cachorro"
    assert response_data["category_id"] == category_id
    assert response_data["image_url"] == (
        "https://example.com/signed-image.webp"
    )

    upload_mock.assert_called_once()

    storage_path, uploaded_content = upload_mock.call_args.args

    assert storage_path.startswith(f"{profile_id}/")
    assert storage_path.endswith(".webp")
    assert uploaded_content.startswith(b"RIFF")

    saved_pictogram = (
        db_session.query(Pictogram)
        .filter(Pictogram.profile_id == profile_id)
        .one()
    )

    assert saved_pictogram.name == "Cachorro"
    assert saved_pictogram.storage_path == storage_path
    assert saved_pictogram.image_url is None
    assert saved_pictogram.content_hash == (
        hashlib.sha256(valid_png).hexdigest()
    )

def test_create_custom_pictogram_rejects_duplicate_file(
    authenticated_client,
    profile_id,
    category_id,
    valid_png,
    db_session,
):
    file_hash = hashlib.sha256(valid_png).hexdigest()

    existing_pictogram = Pictogram(
        name="Cachorro",
        image_url=None,
        storage_path=f"{profile_id}/existing.webp",
        content_hash=file_hash,
        profile_id=profile_id,
        category_id=category_id,
    )

    db_session.add(existing_pictogram)
    db_session.commit()

    with patch(
        "app.routes.custom_pictograms.upload_pictogram_image"
    ) as upload_mock:

        response = authenticated_client.post(
            f"/profiles/{profile_id}/pictograms",
            data={
                "name": "Meu cachorro",
                "category_id": str(category_id),
            },
            files={
                "image": ("cachorro.png", valid_png, "image/png"),
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Este arquivo ja foi enviado para este perfil."
    )

    upload_mock.assert_not_called()

    pictogram_count = (
        db_session.query(Pictogram)
        .filter(Pictogram.profile_id == profile_id)
        .count()
    )

    assert pictogram_count == 1

def test_create_custom_pictogram_rejects_limit(
    authenticated_client,
    profile_id,
    category_id,
    valid_png,
    db_session,
):
    existing_pictograms = [
        Pictogram(
            name=f"Pictogram {index}",
            image_url=None,
            storage_path=f"{profile_id}/{index}.webp",
            content_hash=hashlib.sha256(
                f"existing-image-{index}".encode()
            ).hexdigest(),
            profile_id=profile_id,
            category_id=category_id,
        )
        for index in range(15)
    ]

    db_session.add_all(existing_pictograms)
    db_session.commit()

    with patch(
        "app.routes.custom_pictograms.upload_pictogram_image"
    ) as upload_mock:

        response = authenticated_client.post(
            f"/profiles/{profile_id}/pictograms",
            data={
                "name": "Decimo sexto pictograma",
                "category_id": str(category_id),
            },
            files={
                "image": ("image.png", valid_png, "image/png"),
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "O perfil atingiu o limite de 15 pictogramas personalizados."
    )

    upload_mock.assert_not_called()

    pictogram_count = (
        db_session.query(Pictogram)
        .filter(Pictogram.profile_id == profile_id)
        .count()
    )

    assert pictogram_count == 15

def test_list_profile_pictograms_respects_profile_ownership(
    authenticated_client,
    profile_id,
    category_id,
    db_session,
):
    # Cria um segundo perfil pertencente ao mesmo usuario.
    second_profile_response = authenticated_client.post(
        "/profiles/",
        json={"name": "Segundo perfil"},
    )

    assert second_profile_response.status_code == 201

    second_profile_id = second_profile_response.json()["id"]

    institutional = Pictogram(
        name="Agua",
        image_url="https://example.com/agua.png",
        storage_path=None,
        content_hash=None,
        profile_id=None,
        category_id=category_id,
    )

    own_custom = Pictogram(
        name="Meu cachorro",
        image_url=None,
        storage_path=f"{profile_id}/cachorro.webp",
        content_hash=hashlib.sha256(b"cachorro").hexdigest(),
        profile_id=profile_id,
        category_id=category_id,
    )

    other_custom = Pictogram(
        name="Outro gato",
        image_url=None,
        storage_path=f"{second_profile_id}/gato.webp",
        content_hash=hashlib.sha256(b"gato").hexdigest(),
        profile_id=second_profile_id,
        category_id=category_id,
    )

    db_session.add_all([
        institutional,
        own_custom,
        other_custom,
    ])
    db_session.commit()

    with patch(
        "app.routes.custom_pictograms.create_pictogram_signed_url",
        return_value="https://example.com/signed-image.webp",
    ):
        response = authenticated_client.get(
            f"/profiles/{profile_id}/pictograms"
        )

    assert response.status_code == 200

    pictograms = response.json()
    pictogram_names = {item["name"] for item in pictograms}

    assert pictogram_names == {"Agua", "Meu cachorro"}
    assert "Outro gato" not in pictogram_names

    custom_response = next(
        item for item in pictograms
        if item["name"] == "Meu cachorro"
    )

    assert custom_response["image_url"] == (
        "https://example.com/signed-image.webp"
    )

def test_user_cannot_list_another_users_profile(
    authenticated_client,
    profile_id,
):
    # Cria uma segunda conta.
    second_user = {
        "email": "another@example.com",
        "password": "AnotherPassword123!",
    }

    register_response = authenticated_client.post(
        "/auth/register",
        json=second_user,
    )

    assert register_response.status_code == 201

    # Faz login com a segunda conta.
    login_response = authenticated_client.post(
        "/auth/login",
        data={
            "username": second_user["email"],
            "password": second_user["password"],
        },
    )

    assert login_response.status_code == 200

    second_user_token = login_response.json()["access_token"]

    # Troca a autenticacao para a segunda conta.
    authenticated_client.headers.update({
        "Authorization": f"Bearer {second_user_token}"
    })

    # Tenta acessar o perfil pertencente ao primeiro usuario.
    response = authenticated_client.get(
        f"/profiles/{profile_id}/pictograms"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Perfil nao encontrado."

def test_delete_custom_pictogram_success(
    authenticated_client,
    profile_id,
    category_id,
    db_session,
):
    pictogram = Pictogram(
        name="Cachorro",
        image_url=None,
        storage_path=f"{profile_id}/cachorro.webp",
        content_hash=hashlib.sha256(b"cachorro").hexdigest(),
        profile_id=profile_id,
        category_id=category_id,
    )

    db_session.add(pictogram)
    db_session.commit()
    db_session.refresh(pictogram)

    pictogram_id = pictogram.id
    storage_path = pictogram.storage_path

    with patch(
        "app.routes.custom_pictograms.delete_pictogram_image"
    ) as delete_mock:

        response = authenticated_client.delete(
            f"/profiles/{profile_id}/pictograms/{pictogram_id}"
        )

    assert response.status_code == 204

    delete_mock.assert_called_once_with(storage_path)

    db_session.expire_all()

    deleted_pictogram = db_session.get(Pictogram, pictogram_id)

    assert deleted_pictogram is None

def test_cannot_delete_pictogram_used_in_board(
    authenticated_client,
    profile_id,
    category_id,
    board_id,
    db_session,
):
    from app.models import BoardItem

    pictogram = Pictogram(
        name="Cachorro",
        image_url=None,
        storage_path=f"{profile_id}/cachorro.webp",
        content_hash=hashlib.sha256(b"cachorro").hexdigest(),
        profile_id=profile_id,
        category_id=category_id,
    )

    db_session.add(pictogram)
    db_session.flush()

    board_item = BoardItem(
        board_id=board_id,
        pictogram_id=pictogram.id,
        position=1,
    )

    db_session.add(board_item)
    db_session.commit()

    pictogram_id = pictogram.id

    with patch(
        "app.routes.custom_pictograms.delete_pictogram_image"
    ) as delete_mock:

        response = authenticated_client.delete(
            f"/profiles/{profile_id}/pictograms/{pictogram_id}"
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Remova o pictograma das pranchas antes de exclui-lo."
    )

    delete_mock.assert_not_called()

    assert db_session.get(Pictogram, pictogram_id) is not None

def test_cannot_delete_another_profiles_pictogram(
    authenticated_client,
    profile_id,
    category_id,
    db_session,
):
    # Cria um segundo perfil da mesma conta.
    second_profile_response = authenticated_client.post(
        "/profiles/",
        json={"name": "Segundo perfil"},
    )

    second_profile_id = second_profile_response.json()["id"]

    # Cria um pictograma pertencente ao segundo perfil.
    pictogram = Pictogram(
        name="Gato",
        image_url=None,
        storage_path=f"{second_profile_id}/gato.webp",
        content_hash=hashlib.sha256(b"gato").hexdigest(),
        profile_id=second_profile_id,
        category_id=category_id,
    )

    db_session.add(pictogram)
    db_session.commit()
    db_session.refresh(pictogram)

    pictogram_id = pictogram.id

    # Tenta excluir o pictograma usando o primeiro perfil.
    with patch(
        "app.routes.custom_pictograms.delete_pictogram_image"
    ) as delete_mock:

        response = authenticated_client.delete(
            f"/profiles/{profile_id}/pictograms/{pictogram_id}"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Pictograma personalizado nao encontrado."
    )

    delete_mock.assert_not_called()

    assert db_session.get(Pictogram, pictogram_id) is not None

def test_general_catalog_only_returns_institutional_pictograms(
    authenticated_client,
    profile_id,
    category_id,
    db_session,
):
    institutional = Pictogram(
        name="Agua",
        image_url="https://example.com/agua.png",
        storage_path=None,
        content_hash=None,
        profile_id=None,
        category_id=category_id,
    )

    custom = Pictogram(
        name="Meu cachorro",
        image_url=None,
        storage_path=f"{profile_id}/cachorro.webp",
        content_hash=hashlib.sha256(b"cachorro").hexdigest(),
        profile_id=profile_id,
        category_id=category_id,
    )

    db_session.add_all([institutional, custom])
    db_session.commit()

    response = authenticated_client.get("/pictograms/")

    assert response.status_code == 200

    pictograms = response.json()
    pictogram_names = {item["name"] for item in pictograms}

    assert "Agua" in pictogram_names
    assert "Meu cachorro" not in pictogram_names

def test_cannot_add_another_profiles_pictogram_to_board(
    authenticated_client,
    profile_id,
    category_id,
    board_id,
    db_session,
):
    # Cria um segundo perfil da mesma conta.
    second_profile_response = authenticated_client.post(
        "/profiles/",
        json={"name": "Segundo perfil"},
    )

    second_profile_id = second_profile_response.json()["id"]

    # Cria um pictograma pertencente ao segundo perfil.
    pictogram = Pictogram(
        name="Gato",
        image_url=None,
        storage_path=f"{second_profile_id}/gato.webp",
        content_hash=hashlib.sha256(b"gato").hexdigest(),
        profile_id=second_profile_id,
        category_id=category_id,
    )

    db_session.add(pictogram)
    db_session.commit()
    db_session.refresh(pictogram)

    # Tenta adicionar o pictograma à prancha do primeiro perfil.
    response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json={
            "pictogram_id": pictogram.id,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Pictograma nao encontrado."
    )

def test_get_institutional_pictogram_by_id(
    authenticated_client,
    category_id,
    db_session,
):
    pictogram = Pictogram(
        name="Agua",
        image_url="https://example.com/agua.png",
        storage_path=None,
        content_hash=None,
        profile_id=None,
        category_id=category_id,
    )

    db_session.add(pictogram)
    db_session.commit()
    db_session.refresh(pictogram)

    response = authenticated_client.get(
        f"/pictograms/{pictogram.id}"
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Agua"
    assert response.json()["image_url"] == (
        "https://example.com/agua.png"
    )

def test_cannot_get_custom_pictogram_from_general_catalog(
    authenticated_client,
    profile_id,
    category_id,
    db_session,
):
    pictogram = Pictogram(
        name="Meu cachorro",
        image_url=None,
        storage_path=f"{profile_id}/cachorro.webp",
        content_hash=hashlib.sha256(b"cachorro").hexdigest(),
        profile_id=profile_id,
        category_id=category_id,
    )

    db_session.add(pictogram)
    db_session.commit()
    db_session.refresh(pictogram)

    response = authenticated_client.get(
        f"/pictograms/{pictogram.id}"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Pictograma nao encontrado."
    )