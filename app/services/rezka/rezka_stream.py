from bs4 import BeautifulSoup

from app.schemas.rezka import MovieResponse, SeriesResponse
from app.services.rezka.rezka_base import RezkaBase
from app.services.rezka.rezka_decoder import StreamDecoder


class RezkaStream(RezkaBase):
    def get_movie_source(self, movie_id: int, translator_id: int):
        response_dict = self.post(
            "/ajax/get_cdn_series/",
            data={
                "id": movie_id,
                "translator_id": translator_id,
                "action": "get_movie",
            },
            is_json=True,
        )

        url_value = response_dict.get("url")
        if not isinstance(url_value, str):
            raise ValueError(f"url must be str, got {type(url_value).__name__}")
        return MovieResponse(urls=StreamDecoder.decode(url_value))

    def get_series_source(
        self, series_id: int, translator_id: int, season: int | None = None, episode: int | None = None
    ):
        data = {
            "id": series_id,
            "translator_id": translator_id,
            "action": "get_episodes",
        }
        if season:
            data["season"] = season
        if episode:
            data["episode"] = episode

        response_dict = self.post("/ajax/get_cdn_series/", data=data, is_json=True)

        season_elems = BeautifulSoup(str(response_dict["seasons"]), "html.parser").select("li")
        seasons: dict[int, list[int]] = {int(season_elem.text[6:]): [] for season_elem in season_elems}
        episode_elems = BeautifulSoup(str(response_dict["episodes"]), "html.parser").select("li")
        for episode_elem in episode_elems:
            seasons[int(str(episode_elem["data-season_id"]))].append(int(str(episode_elem["data-episode_id"])))

        return SeriesResponse(
            seasons=seasons,
            urls=StreamDecoder.decode(str(response_dict["url"])),
        )


# response = post(
#     self.URL.join("/engine/ajax/gettrailervideo.php"),
#     # params={"t": 1754934657740},
#     data={
#         "id": 55648,
#     }
# )
#
# print(response.json())

rezka_stream = RezkaStream()

if __name__ == "__main__":
    # print(rezka_stream.get_movie_source(17292, 110))
    # print(rezka_stream.get_movie_source(55648, 110))

    print(rezka_stream.get_series_source(2136, 66))
    # print(rezka_stream.get_series_source(81473, 35, 1, 2))
    # print(rezka_stream.get_series_source(81086, 35, 1, 5))
