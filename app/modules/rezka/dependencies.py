from app.modules.rezka.service import RezkaService, RezkaStream

_rezka_service = RezkaService()
_rezka_stream = RezkaStream()


def get_rezka_service() -> RezkaService:
    return _rezka_service


def get_rezka_stream() -> RezkaStream:
    return _rezka_stream
