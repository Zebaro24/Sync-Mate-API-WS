import pytest

from app.schemas.rezka import MovieResponse, SeriesResponse
from app.services.rezka.rezka_decoder import StreamDecoder
from app.services.rezka.rezka_stream import RezkaStream


@pytest.fixture
def service():
    return RezkaStream()


def test_get_movie_source_decodes(service, mocker):
    fake_decoded = {"720p": "url1.mp4", "1080p": "url2.mp4"}

    mocker.patch.object(StreamDecoder, "decode", return_value=fake_decoded)

    response_dict = {"url": "fake_base64"}
    mocker.patch.object(service, "post", return_value=response_dict)

    result = service.get_movie_source(123, 456)
    assert isinstance(result, MovieResponse)
    assert result.urls == fake_decoded


def test_get_series_source_decodes(service, mocker):
    fake_decoded = {"720p": "url1.mp4", "1080p": "url2.mp4"}
    mocker.patch.object(StreamDecoder, "decode", return_value=fake_decoded)

    response_dict = {
        "url": "fake_base64",
        "seasons": "<li>Season 1</li><li>Season 2</li>",
        "episodes": (
            '<li data-season_id="1" data-episode_id="1"></li>'
            '<li data-season_id="1" data-episode_id="2"></li>'
            '<li data-season_id="2" data-episode_id="1"></li>'
        ),
    }
    mocker.patch.object(service, "post", return_value=response_dict)

    result = service.get_series_source(123, 456)
    assert isinstance(result, SeriesResponse)
    assert result.urls == fake_decoded
    assert result.seasons == {1: [1, 2], 2: [1]}
