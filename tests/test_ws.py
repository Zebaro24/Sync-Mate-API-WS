from tests.client import client


def test_websocket_echo():
    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_text()
        assert data == "Welcome to WebSocket!"
        websocket.send_text("Hello")
        data = websocket.receive_text()
        assert data == "You said: Hello"
