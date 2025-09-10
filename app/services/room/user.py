from fastapi import WebSocket


class User:
    def __init__(self, name: str, websocket: WebSocket):
        print(f"New user {name} connected {websocket.client}")
        self.name = name
        self.websocket = websocket

        self.current_time = 0
        self.downloaded_time = 0

        self.info = {}
