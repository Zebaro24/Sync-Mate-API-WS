import re
from typing import List

from app.services.rezka.rezka_base import RezkaBase
from app.services.rezka.rezka_schemas import (
    InfoMovieResponse,
    MovieQuickSearchResponse,
    MovieSearchResponse,
    QuickInfoMovieResponse,
)


class RezkaService(RezkaBase):
    def quick_search(self, movie_name: str) -> List[MovieQuickSearchResponse]:
        soup = self.post("/engine/ajax/search.php", data={"q": movie_name})

        search_res = []
        for item in soup.select("li a"):
            title_elem = item.select_one("span.enty")

            movie_id = int(re.search(r"/(\d+)-", item["href"]).group(1))
            title = self.get_text(title_elem)
            alter_title = self.get_text(title_elem.next_sibling)
            url = item["href"]
            rating = self.get_text(item.select_one("i.hd-tooltip"))

            search_res.append(
                MovieQuickSearchResponse(
                    id=movie_id,
                    title=title,
                    alter_title=alter_title,
                    rating=rating,
                    url=url,
                )
            )

        return search_res

    def quick_info_movie(self, movie_id: int) -> QuickInfoMovieResponse:
        soup = self.post(
            "/engine/ajax/quick_content.php",
            data={"id": movie_id, "is_touch": 1},
        )

        category = self.get_text(soup.select_one("div.b-content__catlabel"))
        title = self.get_text(soup.select_one("div.b-content__bubble_title"))
        rating = self.get_text(soup.select_one("div.b-content__bubble_rating"))
        description = self.get_text(soup.select_one("div.b-content__bubble_text"))

        genre_elem = soup.select(".b-content__bubble_text")[-1]
        genres = [self.get_text(genre) for genre in genre_elem.select("a")]

        return QuickInfoMovieResponse(
            id=movie_id,
            title=title,
            category=category,
            description=description,
            genres=genres,
            rating=rating,
        )

    def search(self, movie_name: str, limit=0) -> List[MovieSearchResponse]:
        soup = self.get(
            "/search/",
            params={"do": "search", "subaction": "search", "q": movie_name},
        )

        search_res = []
        movie_elems = soup.select("div.b-content__inline_item", limit=limit)
        for movie_elem in movie_elems:
            inline_elem = movie_elem.select_one("div.b-content__inline_item-link")

            movie_id = int(movie_elem["data-id"])
            title = self.get_text(inline_elem.select_one("a"))
            category = self.get_text(movie_elem.select_one("span.cat"))
            caption = self.get_text(inline_elem.select_one("div"))
            image = movie_elem.select_one("img")["src"]
            url = movie_elem["data-url"]

            search_res.append(
                MovieSearchResponse(
                    id=movie_id,
                    title=title,
                    category=category,
                    caption=caption,
                    image=image,
                    url=url,
                )
            )

        return search_res

    def info_movie(self, movie_url: str) -> InfoMovieResponse:
        soup = self.get(movie_url)

        re_player_initializer = re.compile(
            r"sof\.tv\.(initCDNMoviesEvents|initCDNSeriesEvents)\((\d+),\s?(\d+),",
        )
        scripts_text = " ".join(s.get_text() for s in soup.select("script"))
        player_initializer_all = re_player_initializer.findall(scripts_text)

        if player_initializer_all:
            content_type, movie_id, translate_id = player_initializer_all[0]

            content_type = "movie" if content_type == "initCDNMoviesEvents" else "series"
            movie_id = int(movie_id)
            translate_id = int(translate_id)
        else:
            movie_id = int(re.search(r"/(\d+)-", movie_url).group(1))
            content_type, translate_id = None, None

        title = self.get_text(soup.select_one("div.b-post__title"))
        alter_title = self.get_text(soup.select_one("div.b-post__origtitle"))
        category = self.get_text(soup.select_one("a.b-topnav__item-link.active_section"))
        description = self.get_text(soup.select_one("div.b-post__description_text"))

        rating = {}
        for site in ("imdb", "kp"):
            elem = soup.select_one(f"span.b-post__info_rates.{site}")
            if elem:
                rating[site] = self.get_text(elem.select_one("span"))

        genre_elems = soup.select('span[itemprop="genre"]')
        genres = []
        for genre in genre_elems:
            genres.append(self.get_text(genre))

        translator_elems = soup.select("li.b-translator__item, a.b-translator__item")
        translators = {}
        for translator_elem in translator_elems:
            translators[int(translator_elem["data-translator_id"])] = self.get_text(translator_elem)
        if not translators and translate_id:
            translators[translate_id] = None

        return InfoMovieResponse(
            id=movie_id,
            title=title,
            alter_title=alter_title,
            category=category,
            description=description,
            genres=genres,
            rating=rating,
            url=movie_url,
            content_type=content_type,
            translators=translators,
        )


rezka_service = RezkaService()

if __name__ == "__main__":
    print(rezka_service.quick_search("Рик и Морти"))
    # print(rezka_service.quick_info_movie(81398))

    # print(rezka_service.search("Рик"))
    # print(rezka_service.info_movie("https://rezka.ag/cartoons/comedy/2136-rik-i-morti-2013-latest.html"))
    # print(rezka_service.info_movie("https://rezka.ag/series/drama/81473-semya-po-sosedstvu-2025.html"))
    print(rezka_service.info_movie("https://rezka.ag/cartoons/adventures/17292-rikki-tikki-tavi-1965.html"))
    # print(rezka_service.info_movie("https://rezka.ag/films/documentary/55648-god-2023.html"))
    # print(rezka_service.info_movie("https://rezka.ag/films/drama/6089-riki-2009.html"))
    # print(rezka_service.info_movie("https://rezka.ag/series/action/81086-spustit-kurok-2025.html"))

    # print(rezka_service.info_movie("https://rezka.ag/films/fiction/81398-holodnoe-hranilische-2026.html"))
