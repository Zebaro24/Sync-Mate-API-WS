from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, field_validator

# Источник видео ограничен только Rezka.
ALLOWED_VIDEO_PREFIX = "https://rezka.ag/"


class RoomCreate(BaseModel):
    name: str
    video_url: str
    current_time: float = 0.0

    @field_validator("video_url")
    @classmethod
    def _validate_video_url(cls, value: str) -> str:
        if not value.startswith(ALLOWED_VIDEO_PREFIX):
            raise ValueError("video_url must start with https://rezka.ag/")
        return value


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    video_url: Optional[str] = None
    current_time: Optional[float] = None

    @field_validator("video_url")
    @classmethod
    def _validate_video_url(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.startswith(ALLOWED_VIDEO_PREFIX):
            raise ValueError("video_url must start with https://rezka.ag/")
        return value


class RoomInternal(RoomCreate):
    room_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserResponse(BaseModel):
    user_id: str
    name: str
    current_time: float
    downloaded_time: float
    info: dict


class RoomResponse(RoomInternal):
    status: str = "waiting"
    users: list[UserResponse] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def link(self) -> str:
        return f"/api/rooms/{self.room_id}/redirect"

    @classmethod
    def from_room(cls, room) -> "RoomResponse":
        if room.is_paused:
            status = "pausing"
        elif room.is_loaded:
            status = "playing"
        else:
            status = "waiting"

        return cls(
            room_id=room.room_id,
            name=room.name,
            video_url=room.video_url,
            current_time=room.current_time,
            created_at=room.created_at,
            status=status,
            users=[
                UserResponse(
                    user_id=str(u.user_id),
                    name=u.name,
                    current_time=u.current_time,
                    downloaded_time=u.downloaded_time,
                    info=u.info,
                )
                for u in room.user_storage
            ],
        )
