from app.models import BoardItem, Pictogram

def test_add_pictogram_to_custom_board(
    authenticated_client,
    board_id,
    pictogram_ids,
):
    response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json={"pictogram_id": pictogram_ids[0]},
    )

    assert response.status_code == 201

    data = response.json()

    assert data["board_id"] == board_id
    assert data["pictogram_id"] == pictogram_ids[0]
    assert data["position"] == 1

    assert data["pictogram"]["name"] == "Agua"
    assert data["pictogram"]["category_name"] == "Alimentacao"
    assert "image_url" in data["pictogram"]
    assert "created_at" in data["pictogram"]


def test_cannot_add_duplicate_pictogram(
    authenticated_client,
    board_id,
    pictogram_ids,
):
    payload = {"pictogram_id": pictogram_ids[0]}

    first_response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json=payload,
    )

    second_response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_add_nonexistent_pictogram(
    authenticated_client,
    board_id,
):
    response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json={"pictogram_id": 99999},
    )

    assert response.status_code == 404


def test_cannot_add_item_to_system_board(
    authenticated_client,
    system_board_id,
    pictogram_ids,
):
    response = authenticated_client.post(
        f"/boards/{system_board_id}/items",
        json={"pictogram_id": pictogram_ids[0]},
    )

    assert response.status_code == 404


def test_list_board_items_in_position_order(
    authenticated_client,
    board_id,
    pictogram_ids,
):
    first_response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json={"pictogram_id": pictogram_ids[0]},
    )

    second_response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json={"pictogram_id": pictogram_ids[1]},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201

    response = authenticated_client.get(
        f"/boards/{board_id}/items"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2
    assert data[0]["position"] == 1
    assert data[1]["position"] == 2

    assert data[0]["pictogram_id"] == pictogram_ids[0]
    assert data[1]["pictogram_id"] == pictogram_ids[1]


def test_list_items_from_system_board(
    authenticated_client,
    system_board_id,
):
    response = authenticated_client.get(
        f"/boards/{system_board_id}/items"
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_items_from_nonexistent_board(
    authenticated_client,
):
    response = authenticated_client.get(
        "/boards/99999/items"
    )

    assert response.status_code == 404

def test_remove_board_item(
    authenticated_client,
    board_id,
    pictogram_ids,
    db_session,
):
    # Adiciona um pictograma a prancha.
    add_response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json={"pictogram_id": pictogram_ids[0]},
    )

    assert add_response.status_code == 201

    item_id = add_response.json()["id"]

    # Remove o item da prancha.
    response = authenticated_client.delete(
        f"/boards/{board_id}/items/{item_id}"
    )

    assert response.status_code == 204
    assert response.content == b""

    # Confirma que o item nao aparece mais na prancha.
    list_response = authenticated_client.get(
        f"/boards/{board_id}/items"
    )

    assert list_response.status_code == 200
    assert list_response.json() == []

    # Confirma que o pictograma continua no catalogo.
    pictogram = db_session.get(Pictogram, pictogram_ids[0])

    assert pictogram is not None


def test_remove_middle_item_reorganizes_positions(
    authenticated_client,
    board_id,
    pictogram_ids,
):
    # Adiciona tres pictogramas na prancha.
    item_responses = []

    for pictogram_id in pictogram_ids:
        response = authenticated_client.post(
            f"/boards/{board_id}/items",
            json={"pictogram_id": pictogram_id},
        )

        assert response.status_code == 201
        item_responses.append(response.json())

    # Remove o item que ocupa a posicao 2.
    middle_item_id = item_responses[1]["id"]

    delete_response = authenticated_client.delete(
        f"/boards/{board_id}/items/{middle_item_id}"
    )

    assert delete_response.status_code == 204

    # Consulta os itens restantes.
    list_response = authenticated_client.get(
        f"/boards/{board_id}/items"
    )

    assert list_response.status_code == 200

    data = list_response.json()

    assert len(data) == 2

    assert [item["position"] for item in data] == [1, 2]

    assert [
        item["pictogram_id"] for item in data
    ] == [
        pictogram_ids[0],
        pictogram_ids[2],
    ]


def test_cannot_remove_item_from_system_board(
    authenticated_client,
    system_board_id,
    pictogram_ids,
    db_session,
):
    # Cria um item diretamente na prancha do sistema.
    board_item = BoardItem(
        board_id=system_board_id,
        pictogram_id=pictogram_ids[0],
        position=1,
    )

    db_session.add(board_item)
    db_session.commit()
    db_session.refresh(board_item)

    response = authenticated_client.delete(
        f"/boards/{system_board_id}/items/{board_item.id}"
    )

    assert response.status_code == 404

    # Confirma que o item original continua existindo.
    existing_item = db_session.get(BoardItem, board_item.id)

    assert existing_item is not None


def test_cannot_remove_nonexistent_item(
    authenticated_client,
    board_id,
):
    response = authenticated_client.delete(
        f"/boards/{board_id}/items/99999"
    )

    assert response.status_code == 404
