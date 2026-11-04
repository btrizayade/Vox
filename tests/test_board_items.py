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

def test_reorder_board_items(
    authenticated_client,
    board_id,
    pictogram_ids,
):
    created_items = []

    for pictogram_id in pictogram_ids:
        response = authenticated_client.post(
            f"/boards/{board_id}/items",
            json={"pictogram_id": pictogram_id},
        )

        assert response.status_code == 201
        created_items.append(response.json())

    new_order = [
        created_items[2]["id"],
        created_items[0]["id"],
        created_items[1]["id"],
    ]

    response = authenticated_client.patch(
        f"/boards/{board_id}/items/reorder",
        json={"item_ids": new_order},
    )

    assert response.status_code == 200

    data = response.json()

    assert [item["id"] for item in data] == new_order
    assert [item["position"] for item in data] == [1, 2, 3]

def test_reorder_requires_all_board_items(
    authenticated_client,
    board_id,
    pictogram_ids,
):
    created_items = []

    for pictogram_id in pictogram_ids:
        response = authenticated_client.post(
            f"/boards/{board_id}/items",
            json={"pictogram_id": pictogram_id},
        )

        assert response.status_code == 201
        created_items.append(response.json())

    response = authenticated_client.patch(
        f"/boards/{board_id}/items/reorder",
        json={
            "item_ids": [
                created_items[0]["id"],
                created_items[1]["id"],
            ]
        },
    )

    assert response.status_code == 422

    # A ordem original deve ser preservada.
    list_response = authenticated_client.get(
        f"/boards/{board_id}/items"
    )

    assert [
        item["id"] for item in list_response.json()
    ] == [
        item["id"] for item in created_items
    ]

def test_reorder_rejects_duplicate_ids(
    authenticated_client,
    board_id,
    pictogram_ids,
):
    response = authenticated_client.post(
        f"/boards/{board_id}/items",
        json={"pictogram_id": pictogram_ids[0]},
    )

    assert response.status_code == 201

    item_id = response.json()["id"]

    response = authenticated_client.patch(
        f"/boards/{board_id}/items/reorder",
        json={"item_ids": [item_id, item_id]},
    )

    assert response.status_code == 422

def test_reorder_rejects_item_from_another_board(
    authenticated_client,
    board_id,
    pictogram_ids,
):
    created_items = []

    for pictogram_id in pictogram_ids[:2]:
        response = authenticated_client.post(
            f"/boards/{board_id}/items",
            json={"pictogram_id": pictogram_id},
        )

        assert response.status_code == 201
        created_items.append(response.json())

    board_response = authenticated_client.get(
        f"/boards/{board_id}"
    )

    profile_id = board_response.json()["profile_id"]

    other_board_response = authenticated_client.post(
        "/boards/",
        json={
            "profile_id": profile_id,
            "name": "Outra prancha",
        },
    )

    assert other_board_response.status_code == 201

    other_board_id = other_board_response.json()["id"]

    foreign_item_response = authenticated_client.post(
        f"/boards/{other_board_id}/items",
        json={"pictogram_id": pictogram_ids[2]},
    )

    assert foreign_item_response.status_code == 201

    foreign_item_id = foreign_item_response.json()["id"]

    response = authenticated_client.patch(
        f"/boards/{board_id}/items/reorder",
        json={
            "item_ids": [
                created_items[0]["id"],
                foreign_item_id,
            ]
        },
    )

    assert response.status_code == 422

def test_cannot_reorder_system_board(
    authenticated_client,
    system_board_id,
    pictogram_ids,
    db_session,
):
    board_item = BoardItem(
        board_id=system_board_id,
        pictogram_id=pictogram_ids[0],
        position=1,
    )

    db_session.add(board_item)
    db_session.commit()
    db_session.refresh(board_item)

    response = authenticated_client.patch(
        f"/boards/{system_board_id}/items/reorder",
        json={"item_ids": [board_item.id]},
    )

    assert response.status_code == 404
