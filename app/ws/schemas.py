from typing import Literal

from pydantic import BaseModel


class ConnectMessage(BaseModel):
    """Initial handshake sent by the client when joining a room."""

    type: Literal["connect"]
    name: str
