from typing import List

from fastapi import APIRouter, Depends

from app.modules.rezka.dependencies import get_rezka_service, get_rezka_stream
from app.modules.rezka.schemas import (
    InfoMovieResponse,
    MovieQuickSearchResponse,
    MovieResponse,
    MovieSearchResponse,
    QuickInfoMovieResponse,
    SeriesResponse,
)
from app.modules.rezka.service import RezkaService, RezkaStream

router = APIRouter(tags=["Rezka"])


@router.get("/quick_search", response_model=List[MovieQuickSearchResponse], tags=["Search"])
async def quick_search(
    movie_title: str,
    service: RezkaService = Depends(get_rezka_service),
) -> List[MovieQuickSearchResponse]:
    return await service.quick_search(movie_title)


@router.get("/search", response_model=List[MovieSearchResponse], tags=["Search"])
async def search(
    movie_title: str,
    limit: int = 0,
    service: RezkaService = Depends(get_rezka_service),
) -> List[MovieSearchResponse]:
    return await service.search(movie_title, limit)


@router.get("/quick_info_movie", response_model=QuickInfoMovieResponse, tags=["Info"])
async def quick_info_movie(
    movie_id: int,
    service: RezkaService = Depends(get_rezka_service),
) -> QuickInfoMovieResponse:
    return await service.quick_info_movie(movie_id)


@router.get("/info_movie", response_model=InfoMovieResponse, tags=["Info"])
async def info_movie(
    movie_url: str,
    service: RezkaService = Depends(get_rezka_service),
) -> InfoMovieResponse:
    return await service.info_movie(movie_url)


@router.get("/movie_source", response_model=MovieResponse, tags=["Stream"])
async def movie_source(
    movie_id: int,
    translator_id: int,
    stream: RezkaStream = Depends(get_rezka_stream),
) -> MovieResponse:
    return await stream.get_movie_source(movie_id, translator_id)


@router.get("/series_source", response_model=SeriesResponse, tags=["Stream"])
async def series_source(
    series_id: int,
    translator_id: int,
    season: int | None = None,
    episode: int | None = None,
    stream: RezkaStream = Depends(get_rezka_stream),
) -> SeriesResponse:
    return await stream.get_series_source(series_id, translator_id, season, episode)
