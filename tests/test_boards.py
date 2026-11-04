from app.models import Board

def test_create_board(authenticated_client, profile_id):
    response = authenticated_client.post(
        "/boards/",
        json={
            "profile_id": profile_id,
            "name": "Prancha de comunicacao",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["profile_id"] == profile_id
    assert data["name"] == "Prancha de comunicacao"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_list_boards(authenticated_client, board_id):
    response = authenticated_client.get("/boards/")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == board_id


def test_get_board(authenticated_client, board_id):
    response = authenticated_client.get(
        f"/boards/{board_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == board_id


def test_update_board(authenticated_client, board_id):
    response = authenticated_client.put(
        f"/boards/{board_id}",
        json={"name": "Rotina atualizada"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Rotina atualizada"


def test_delete_board(authenticated_client, board_id):
    response = authenticated_client.delete(
        f"/boards/{board_id}"
    )

    assert response.status_code == 204

    # Confirma que a prancha foi realmente excluida
    get_response = authenticated_client.get(
        f"/boards/{board_id}"
    )

    assert get_response.status_code == 404


def test_get_nonexistent_board(authenticated_client):
    response = authenticated_client.get("/boards/9999")

    assert response.status_code == 404


def test_boards_require_authentication(client):
    response = client.get("/boards/")

    assert response.status_code == 401


def test_user_cannot_access_another_users_board(
    authenticated_client,
    profile_id,
    board_id,
):
    # Registra um segundo usuario
    second_user = {
        "email": "second@example.com",
        "password": "TestPassword456!",
    }

    register_response = authenticated_client.post(
        "/auth/register",
        json=second_user,
    )

    assert register_response.status_code == 201

    # Autentica o segundo usuario
    login_response = authenticated_client.post(
        "/auth/login",
        data={
            "username": second_user["email"],
            "password": second_user["password"],
        },
    )

    assert login_response.status_code == 200

    second_token = login_response.json()["access_token"]

    authenticated_client.headers.update({
        "Authorization": f"Bearer {second_token}"
    })

    # Tenta consultar a prancha do primeiro usuario
    board_response = authenticated_client.get(
        f"/boards/{board_id}"
    )

    assert board_response.status_code == 404

    # Tenta listar as pranchas do primeiro usuario
    list_response = authenticated_client.get("/boards/")

    assert list_response.status_code == 200
    assert list_response.json() == []

    # Tenta criar uma prancha usando o perfil de outro usuario
    create_response = authenticated_client.post(
        "/boards/",
        json={
            "profile_id": profile_id,
            "name": "Prancha nao autorizada",
        },
    )

    assert create_response.status_code == 404

def test_list_system_boards(
    authenticated_client,
    system_board_id,
):
    response = authenticated_client.get("/boards/system")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == system_board_id
    assert data[0]["name"] == "Escola"
    assert data[0]["board_type"] == "system"
    assert data[0]["profile_id"] is None


def test_user_can_get_system_board(
    authenticated_client,
    system_board_id,
):
    response = authenticated_client.get(
        f"/boards/{system_board_id}"
    )

    assert response.status_code == 200
    assert response.json()["board_type"] == "system"


def test_system_boards_do_not_appear_in_custom_list(
    authenticated_client,
    system_board_id,
):
    response = authenticated_client.get("/boards/")

    assert response.status_code == 200
    assert response.json() == []


def test_user_cannot_update_system_board(
    authenticated_client,
    system_board_id,
):
    response = authenticated_client.put(
        f"/boards/{system_board_id}",
        json={"name": "Escola modificada"},
    )

    assert response.status_code == 404


def test_user_cannot_delete_system_board(
    authenticated_client,
    system_board_id,
    db_session,
):
    response = authenticated_client.delete(
        f"/boards/{system_board_id}"
    )

    assert response.status_code == 404

    board = db_session.get(Board, system_board_id)

    assert board is not None
    assert board.name == "Escola"


def test_user_cannot_create_system_board(
    authenticated_client,
    profile_id,
):
    response = authenticated_client.post(
        "/boards/",
        json={
            "profile_id": profile_id,
            "name": "Prancha nao autorizada",
            "board_type": "system",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["board_type"] == "custom"
    assert data["profile_id"] == profile_id
