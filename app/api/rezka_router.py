from typing import List

from fastapi import APIRouter

from app.schemas.rezka import (
    InfoMovieResponse,
    MovieQuickSearchResponse,
    MovieResponse,
    MovieSearchResponse,
    QuickInfoMovieResponse,
    SeriesResponse,
)
from app.services.rezka.rezka_service import rezka_service
from app.services.rezka.rezka_stream import rezka_stream

router = APIRouter()


@router.get("/quick_search", tags=["Rezka", "Search"], response_model=List[MovieQuickSearchResponse])
async def quick_search(movie_title: str):
    return rezka_service.quick_search(movie_title)


@router.get("/search", tags=["Rezka", "Search"], response_model=List[MovieSearchResponse])
async def search(movie_title: str, limit: int = 0):
    return rezka_service.search(movie_title, limit)


@router.get("/quick_info_movie", tags=["Rezka", "Info"], response_model=QuickInfoMovieResponse)
async def quick_info_movie(movie_id: int):
    return rezka_service.quick_info_movie(movie_id)


@router.get("/info_movie", tags=["Rezka", "Info"], response_model=InfoMovieResponse)
async def info_movie(movie_url: str):
    return rezka_service.info_movie(movie_url)


@router.get("/movie_source", tags=["Rezka", "Stream"], response_model=MovieResponse)
async def movie_source(movie_id: int, translator_id: int):
    return rezka_stream.get_movie_source(movie_id, translator_id)


@router.get("/series_source", tags=["Rezka", "Stream"], response_model=SeriesResponse)
async def series_source(series_id: int, translator_id: int, season: int = None, episode: int = None):
    return rezka_stream.get_series_source(series_id, translator_id, season, episode)
