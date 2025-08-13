from typing import List
from uuid import uuid4

from fastapi import WebSocket


class Room:
    def __init__(self):
        self.id = str(uuid4())

        self.video_name: str = ""
        self.video_time = None

        self.client_storage: List[WebSocket] = []

    def add_client(self, client):
        self.client_storage.append(client)

    def remove_client(self, client):
        self.client_storage.remove(client)

    def get_clients_exc(self, exception_client=None):
        return [client for client in self.client_storage if client != exception_client]

    def __str__(self):
        return f"<Room {self.id}: clients={[websocket.client for websocket in self.client_storage]}>"
