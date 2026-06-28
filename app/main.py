import logging.config

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router as api_router
from app.config import settings
from app.ws.router import router as ws_router

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "app": {
            "handlers": ["console"],
            # Временно форсировано в DEBUG для ловли багов (штатно: "DEBUG" if settings.debug else "INFO").
            # Уровень логов развязан с settings.debug — подробные логи НЕ открывают /api/rooms и FastAPI-traceback.
            "level": "DEBUG",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

app = FastAPI(
    title=settings.app_name,
    description=settings.description,
    version=settings.version,
    debug=settings.debug,
)

# API публичный и без авторизации: расширение зовёт его с разных origin (страница Rezka,
# chrome-extension://…) и НЕ шлёт куки/credentials. Поэтому origin оставляем "*", но
# allow_credentials=False — иначе связка "*" + credentials позволяет любому сайту дёргать API
# в контексте пользователя. Сужать origin списком нельзя (id расширения/origin не фиксированы).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")
app.include_router(ws_router, prefix="/ws")
