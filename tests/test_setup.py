def test_api_root_returns_success(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "message" in response.json()