from random import choice

from bs4 import BeautifulSoup, Tag
from httpx import URL, get, post

from app.config import settings


class RezkaBase:
    URL = URL(settings.REZKA_URL)
    PROXIES_LIST = settings.PROXIES_LIST

    def _get_random_proxy(self):
        if not self.PROXIES_LIST:
            return None
        return choice(self.PROXIES_LIST)  # nosec B311

    @staticmethod
    def _parse_response(response, is_json) -> dict | BeautifulSoup:
        if is_json:
            return response.json()

        soup = BeautifulSoup(response.text, "html.parser")
        return soup

    def get(self, url: str, params=None, is_json=False) -> dict | BeautifulSoup:
        response = get(self.URL.join(url), params=params, proxy=self._get_random_proxy())
        return self._parse_response(response, is_json)

    def post(self, url, data=None, is_json=False) -> dict | BeautifulSoup:
        response = post(self.URL.join(url), data=data, proxy=self._get_random_proxy())
        return self._parse_response(response, is_json)

    @staticmethod
    def get_text(tag: None | Tag) -> None | str:
        if tag is None:
            return None
        return tag.text.strip()
