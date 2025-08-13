from bs4 import BeautifulSoup, Tag
from httpx import URL, get, post

from app.config import settings


class RezkaBase:
    URL = URL(settings.REZKA_URL)

    @staticmethod
    def _parse_response(response, is_json) -> dict | BeautifulSoup:
        if is_json:
            return response.json()

        soup = BeautifulSoup(response.text, "html.parser")
        return soup

    def get(self, url: str, params=None, is_json=False) -> dict | BeautifulSoup:
        response = get(self.URL.join(url), params=params)
        return self._parse_response(response, is_json)

    def post(self, url, data=None, is_json=False) -> dict | BeautifulSoup:
        response = post(self.URL.join(url), data=data)
        return self._parse_response(response, is_json)

    @staticmethod
    def get_text(tag: None | Tag) -> None | str:
        if tag is None:
            return None
        return tag.text.strip()
