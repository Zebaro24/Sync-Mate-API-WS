from typing import Any

from fastapi import WebSocket


class User:
    def __init__(self, name: str, websocket: WebSocket):
        print(f"New user {name} connected {websocket.client}")
        self.user_id = id(self)
        self.name = name
        self.websocket = websocket

        self.current_time = 0
        self.downloaded_time = 0

        self.info: dict[str, Any] = {}
