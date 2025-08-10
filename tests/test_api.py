from tests.client import client


def test_info():
    response = client.get("/info")
    assert response.status_code == 200
    assert response.json().get('name') == "Sync-Mate-API-WS"
