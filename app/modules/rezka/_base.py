import logging
from random import choice
from typing import Literal, Union, cast, overload

import httpx
from bs4 import BeautifulSoup, PageElement, Tag

from app.config import settings

logger = logging.getLogger(__name__)

# Таймауты подобраны под публичный rezka.ag, который иногда отвечает медленно.
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=10.0, pool=5.0)


class RezkaBase:
    URL = httpx.URL(settings.REZKA_URL)
    PROXIES_LIST = settings.PROXIES_LIST

    def _get_random_proxy(self) -> str | None:
        if not self.PROXIES_LIST:
            return None
        return cast(str, choice(self.PROXIES_LIST))  # nosec B311

    @staticmethod
    def _parse_response(response: httpx.Response, is_json: bool) -> Union[dict, BeautifulSoup]:
        if is_json:
            return cast(dict, response.json())
        return BeautifulSoup(response.text, "html.parser")

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params=None,
        data=None,
        is_json: bool = False,
    ) -> Union[dict, BeautifulSoup]:
        proxy = self._get_random_proxy()
        async with httpx.AsyncClient(proxy=proxy, timeout=_DEFAULT_TIMEOUT, follow_redirects=True) as client:
            try:
                response = await client.request(method, self.URL.join(url), params=params, data=data)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning("Rezka %s %s failed: %s", method, url, exc)
                raise
        return self._parse_response(response, is_json)

    @overload
    async def get(self, url: str, params=None, is_json: Literal[False] = ...) -> BeautifulSoup: ...

    @overload
    async def get(self, url: str, params=None, is_json: Literal[True] = ...) -> dict: ...

    async def get(self, url: str, params=None, is_json: bool = False):
        return await self._request("GET", url, params=params, is_json=is_json)

    @overload
    async def post(self, url: str, data=None, is_json: Literal[False] = ...) -> BeautifulSoup: ...

    @overload
    async def post(self, url: str, data=None, is_json: Literal[True] = ...) -> dict: ...

    async def post(self, url: str, data=None, is_json: bool = False):
        return await self._request("POST", url, data=data, is_json=is_json)

    @staticmethod
    def get_text(tag: Tag | PageElement | None) -> str | None:
        if tag is None:
            return None
        return str(tag.text).strip()
