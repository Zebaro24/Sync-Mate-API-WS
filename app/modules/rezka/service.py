import logging
import re
from typing import List

from bs4 import BeautifulSoup

from app.modules.rezka._base import RezkaBase
from app.modules.rezka._decoder import StreamDecoder
from app.modules.rezka.schemas import (
    InfoMovieResponse,
    MovieQuickSearchResponse,
    MovieResponse,
    MovieSearchResponse,
    QuickInfoMovieResponse,
    SeriesResponse,
)

logger = logging.getLogger(__name__)

# Извлечение числового ID сезона из текста ("Сезон 2", "Season 2", "2-й сезон" и т.п.).
_SEASON_NUMBER_RE = re.compile(r"\d+")


class RezkaService(RezkaBase):
    async def quick_search(self, movie_name: str) -> List[MovieQuickSearchResponse]:
        soup = await self.post("/engine/ajax/search.php", data={"q": movie_name})

        results = []
        for item in soup.select("li a"):
            title_elem = item.select_one("span.enty")
            href = str(item.get("href", ""))

            match = re.search(r"/(\d+)-", href)
            if match is None:
                # Иногда rezka подмешивает строки-разделители без id — пропускаем.
                continue

            results.append(
                MovieQuickSearchResponse(
                    id=int(match.group(1)),
                    title=self.get_text(title_elem) or "",
                    alter_title=self.get_text(title_elem.next_sibling if title_elem else None) or "",
                    url=href,
                    rating=self.get_text(item.select_one("i.hd-tooltip")),
                )
            )
        return results

    async def quick_info_movie(self, movie_id: int) -> QuickInfoMovieResponse:
        soup = await self.post(
            "/engine/ajax/quick_content.php",
            data={"id": movie_id, "is_touch": 1},
        )

        bubble_texts = soup.select(".b-content__bubble_text")
        # Последний блок .b-content__bubble_text обычно содержит жанры, но он может
        # отсутствовать при отсутствии фильма — отдаём пустой список без падения.
        genres = [self.get_text(g) or "" for g in bubble_texts[-1].select("a")] if bubble_texts else []
        return QuickInfoMovieResponse(
            id=movie_id,
            category=self.get_text(soup.select_one("div.b-content__catlabel")) or "",
            title=self.get_text(soup.select_one("div.b-content__bubble_title")) or "",
            rating=self.get_text(soup.select_one("div.b-content__bubble_rating")),
            description=self.get_text(soup.select_one("div.b-content__bubble_text")) or "",
            genres=genres,
        )

    async def search(self, movie_name: str, limit: int = 0) -> List[MovieSearchResponse]:
        soup = await self.get(
            "/search/",
            params={"do": "search", "subaction": "search", "q": movie_name},
        )

        results = []
        for movie_elem in soup.select("div.b-content__inline_item", limit=limit):
            inline_elem = movie_elem.select_one("div.b-content__inline_item-link")
            img_tag = movie_elem.select_one("img")
            results.append(
                MovieSearchResponse(
                    id=int(str(movie_elem["data-id"])),
                    title=self.get_text(inline_elem.select_one("a") if inline_elem else None) or "",
                    category=self.get_text(movie_elem.select_one("span.cat")) or "",
                    caption=self.get_text(inline_elem.select_one("div") if inline_elem else None) or "",
                    image=str(img_tag["src"]) if img_tag and img_tag.get("src") else "",
                    url=str(movie_elem.get("data-url", "")),
                )
            )
        return results

    async def info_movie(self, movie_url: str) -> InfoMovieResponse:
        soup = await self.get(movie_url)

        re_player_initializer = re.compile(r"sof\.tv\.(initCDNMoviesEvents|initCDNSeriesEvents)\((\d+),\s?(\d+),")
        scripts_text = " ".join(s.get_text() for s in soup.select("script"))
        player_matches = re_player_initializer.findall(scripts_text)

        if player_matches:
            content_type_raw, movie_id_str, translator_id_str = player_matches[0]
            content_type = "movie" if content_type_raw == "initCDNMoviesEvents" else "series"
            movie_id = int(movie_id_str)
            translate_id: int | None = int(translator_id_str)
        else:
            match = re.search(r"/(\d+)-", movie_url)
            if match is None:
                raise ValueError(f"Cannot extract movie_id from URL: {movie_url}")
            movie_id = int(match.group(1))
            content_type, translate_id = None, None

        rating: dict[str, str] = {}
        for site in ("imdb", "kp"):
            elem = soup.select_one(f"span.b-post__info_rates.{site}")
            if elem:
                text = self.get_text(elem.select_one("span"))
                if text is not None:
                    rating[site] = text

        genres = [text for g in soup.select('span[itemprop="genre"]') if (text := self.get_text(g)) is not None]

        translators: dict[int, str | None] = {}
        for elem in soup.select("li.b-translator__item, a.b-translator__item"):
            tid_str = elem.get("data-translator_id")
            if tid_str is None:
                continue
            translators[int(str(tid_str))] = self.get_text(elem)
        if not translators and translate_id:
            translators[translate_id] = None

        return InfoMovieResponse(
            id=movie_id,
            title=self.get_text(soup.select_one("div.b-post__title")) or "",
            alter_title=self.get_text(soup.select_one("div.b-post__origtitle")) or "",
            category=self.get_text(soup.select_one("a.b-topnav__item-link.active_section")) or "",
            description=self.get_text(soup.select_one("div.b-post__description_text")) or "",
            rating=rating,
            genres=genres,
            url=movie_url,
            content_type=content_type,
            translators=translators,
        )


class RezkaStream(RezkaBase):
    async def get_movie_source(self, movie_id: int, translator_id: int) -> MovieResponse:
        response = await self.post(
            "/ajax/get_cdn_series/",
            data={"id": movie_id, "translator_id": translator_id, "action": "get_movie"},
            is_json=True,
        )
        url_value = response.get("url")
        if not isinstance(url_value, str):
            raise ValueError(f"url must be str, got {type(url_value).__name__}")
        return MovieResponse(urls=StreamDecoder.decode(url_value))

    async def get_series_source(
        self,
        series_id: int,
        translator_id: int,
        season: int | None = None,
        episode: int | None = None,
    ) -> SeriesResponse:
        data: dict = {"id": series_id, "translator_id": translator_id, "action": "get_episodes"}
        if season:
            data["season"] = season
        if episode:
            data["episode"] = episode

        response = await self.post("/ajax/get_cdn_series/", data=data, is_json=True)

        season_elems = BeautifulSoup(str(response["seasons"]), "html.parser").select("li")
        seasons: dict[int, list[int]] = {}
        for elem in season_elems:
            sid_attr = elem.get("data-tab_id") or elem.get("data-season_id")
            if sid_attr is not None:
                seasons[int(str(sid_attr))] = []
                continue
            # Фолбэк: извлекаем число из текста, что устойчивее к смене локали.
            match = _SEASON_NUMBER_RE.search(elem.get_text())
            if match:
                seasons[int(match.group(0))] = []

        episode_elems = BeautifulSoup(str(response["episodes"]), "html.parser").select("li")
        for elem in episode_elems:
            season_id: int = int(str(elem["data-season_id"]))
            episode_id: int = int(str(elem["data-episode_id"]))
            seasons.setdefault(season_id, []).append(episode_id)

        return SeriesResponse(
            seasons=seasons,
            urls=StreamDecoder.decode(str(response["url"])),
        )
