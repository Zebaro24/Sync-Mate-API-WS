from typing import Dict, List, Optional

from pydantic import BaseModel


class MovieQuickSearchResponse(BaseModel):
    id: int
    title: str
    alter_title: str
    rating: Optional[str]
    url: str


class QuickInfoMovieResponse(BaseModel):
    id: int
    title: str
    category: str
    description: str
    genres: List[str]
    rating: Optional[str]


class MovieSearchResponse(BaseModel):
    id: int
    title: str
    category: str
    caption: str
    image: str
    url: str


class InfoMovieResponse(BaseModel):
    id: int
    title: str
    alter_title: Optional[str]
    category: str
    description: str
    genres: List[str]
    rating: Optional[Dict[str, str]]
    url: str
    content_type: Optional[str]
    translators: Dict[int, str | None]


class MovieResponse(BaseModel):
    urls: Dict[str, str]


class SeriesResponse(BaseModel):
    seasons: Dict[int, List[int]]
    urls: Dict[str, str]
