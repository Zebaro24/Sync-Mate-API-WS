from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sync-Mate-API-WS"
    description: str = (
        "SyncMate API WS is a REST and WebSocket service "
        "providing synchronized video playback control, "
        "metadata streams, and video sources retrieval "
        "from YouTube and Rezka.ag."
    )
    author: str = "Zebaro (zebaro.dev)"
    version: str = "0.0.1"

    debug: bool = True

    REZKA_URL: str = "https://rezka.ag"

    PROXIES_LIST: list | str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if isinstance(self.PROXIES_LIST, str):
            self.PROXIES_LIST = [p.strip() for p in self.PROXIES_LIST.split(",")]


settings = Settings()
