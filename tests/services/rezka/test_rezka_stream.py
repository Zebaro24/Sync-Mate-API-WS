from unittest.mock import AsyncMock

import pytest

from app.modules.rezka._decoder import StreamDecoder
from app.modules.rezka.schemas import MovieResponse, SeriesResponse
from app.modules.rezka.service import RezkaStream


@pytest.fixture
def service():
    return RezkaStream()


@pytest.mark.asyncio
async def test_get_movie_source_decodes(service, mocker):
    fake_decoded = {"720p": "url1.mp4", "1080p": "url2.mp4"}

    mocker.patch.object(StreamDecoder, "decode", return_value=fake_decoded)

    response_dict = {"url": "fake_base64"}
    mocker.patch.object(service, "post", AsyncMock(return_value=response_dict))

    result = await service.get_movie_source(123, 456)
    assert isinstance(result, MovieResponse)
    assert result.urls == fake_decoded


@pytest.mark.asyncio
async def test_get_series_source_decodes(service, mocker):
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
    mocker.patch.object(service, "post", AsyncMock(return_value=response_dict))

    result = await service.get_series_source(123, 456)
    assert isinstance(result, SeriesResponse)
    assert result.urls == fake_decoded
    assert result.seasons == {1: [1, 2], 2: [1]}


@pytest.mark.asyncio
async def test_get_series_source_with_localized_season_names(service, mocker):
    """Парсер должен находить номер сезона даже если текст не 'Season X'."""
    mocker.patch.object(StreamDecoder, "decode", return_value={})

    response_dict = {
        "url": "x",
        "seasons": "<li>Сезон 1</li><li>Сезон 2</li>",
        "episodes": '<li data-season_id="1" data-episode_id="1"></li>',
    }
    mocker.patch.object(service, "post", AsyncMock(return_value=response_dict))

    result = await service.get_series_source(123, 456)
    assert 1 in result.seasons
    assert 2 in result.seasons
