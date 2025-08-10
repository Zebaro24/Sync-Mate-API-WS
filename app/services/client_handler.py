import asyncio

from fastapi import WebSocket

from app.core.room import Room


class ClientHandler:
    ACTION_TYPES = ["play", "pause", "buffering"]

    def __init__(self, room: Room, client: WebSocket):
        self.room = room
        self.client = client

    async def send_to_room(self, data: dict):
        clients = self.room.get_clients_exc(self.client)
        await asyncio.gather(*(client.send_json(data) for client in clients))

    async def handle(self, data: dict):
        if data.get("type") not in self.ACTION_TYPES:
            return
        video_time = data.get("video_time")
        self.room.video_time = video_time
        await self.send_to_room(data)
