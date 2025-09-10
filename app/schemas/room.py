from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field

from app.services.room.room import Room


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    video_url: Optional[str] = None
    current_time: Optional[float] = None


class RoomRequest(BaseModel):
    name: str

    video_url: str
    current_time: Optional[float] = 0


class RoomSchema(RoomRequest):
    room_id: str = Field(default_factory=lambda: str(uuid4()))

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoomResponse(RoomSchema):
    status: str = "waiting"
    users: list[dict] = []

    @computed_field
    @property
    def link(self) -> str:
        return f"/rooms/{self.room_id}/redirect"

    @classmethod
    def from_room(cls, room: Room):
        status = "pausing" if room.is_paused else ("playing" if room.is_loaded else "waiting")
        return cls(
            room_id=room.room_id,
            name=room.name,
            video_url=room.video_url,
            current_time=room.current_time,
            created_at=room.created_at,
            status=status,
            users=[
                {
                    "user_id": u.user_id,
                    "name": u.name,
                    "current_time": u.current_time,
                    "downloaded_time": u.downloaded_time,
                    "info": u.info,
                }
                for u in room.user_storage
            ],
        )
