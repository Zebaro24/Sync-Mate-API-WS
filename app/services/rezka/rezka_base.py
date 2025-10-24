from random import choice
from typing import Literal, Union, overload

from bs4 import BeautifulSoup, PageElement, Tag
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
    def _parse_response(response, is_json) -> Union[dict, BeautifulSoup]:
        if is_json:
            res: dict = response.json()
            return res

        soup = BeautifulSoup(response.text, "html.parser")
        return soup

    @overload
    def get(self, url: str, params=None, is_json: Literal[False] = ...) -> BeautifulSoup: ...

    @overload
    def get(self, url: str, params=None, is_json: Literal[True] = ...) -> dict: ...

    def get(self, url: str, params=None, is_json=False):
        response = get(self.URL.join(url), params=params, proxy=self._get_random_proxy())
        return self._parse_response(response, is_json)

    @overload
    def post(self, url: str, data=None, is_json: Literal[False] = ...) -> BeautifulSoup: ...

    @overload
    def post(self, url: str, data=None, is_json: Literal[True] = ...) -> dict: ...

    def post(self, url, data=None, is_json=False):
        response = post(self.URL.join(url), data=data, proxy=self._get_random_proxy())
        return self._parse_response(response, is_json)

    @staticmethod
    def get_text(tag: Tag | PageElement | None) -> None | str:
        if tag is None:
            return None
        return str(tag.text).strip()
