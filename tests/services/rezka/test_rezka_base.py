from unittest.mock import AsyncMock, MagicMock

import pytest
from bs4 import BeautifulSoup

from app.modules.rezka._base import RezkaBase


def test_get_random_proxy_returns_none_when_empty():
    base = RezkaBase()
    base.PROXIES_LIST = []
    assert base._get_random_proxy() is None


def test_get_random_proxy_returns_one_of_list():
    base = RezkaBase()
    base.PROXIES_LIST = ["https://1", "https://2"]
    result = base._get_random_proxy()
    assert result in base.PROXIES_LIST


def test_parse_response_json(mocker):
    base = RezkaBase()
    response = mocker.MagicMock()
    response.json.return_value = {"ok": True}

    result = base._parse_response(response, is_json=True)
    assert result == {"ok": True}


def test_parse_response_html(mocker):
    base = RezkaBase()
    response = mocker.MagicMock()
    response.text = "<html><body><p>Hello</p></body></html>"

    result = base._parse_response(response, is_json=False)
    assert isinstance(result, BeautifulSoup)
    assert result.p is not None
    assert result.p.text == "Hello"


@pytest.mark.asyncio
async def test_get_calls_request(mocker):
    base = RezkaBase()
    expected = BeautifulSoup("<html></html>", "html.parser")
    mock_request = AsyncMock(return_value=expected)
    mocker.patch.object(RezkaBase, "_request", mock_request)

    result = await base.get("/page", params={"q": 1})

    mock_request.assert_awaited_once()
    assert result is expected


@pytest.mark.asyncio
async def test_post_calls_request(mocker):
    base = RezkaBase()
    expected = BeautifulSoup("<html></html>", "html.parser")
    mock_request = AsyncMock(return_value=expected)
    mocker.patch.object(RezkaBase, "_request", mock_request)

    result = await base.post("/submit", data={"a": 1})

    mock_request.assert_awaited_once()
    assert result is expected


@pytest.mark.asyncio
async def test_request_raises_for_status(mocker):
    """При HTTP-ошибке _request должен пробросить httpx.HTTPError."""
    import httpx

    base = RezkaBase()

    class _MockResponse:
        text = ""

        def raise_for_status(self):
            raise httpx.HTTPStatusError("boom", request=MagicMock(), response=MagicMock())

        def json(self):  # pragma: no cover
            return {}

    class _MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            return _MockResponse()

    mocker.patch("app.modules.rezka._base.httpx.AsyncClient", return_value=_MockClient())

    with pytest.raises(httpx.HTTPError):
        await base._request("GET", "/page")


def test_get_text_returns_none_if_tag_none():
    assert RezkaBase.get_text(None) is None


def test_get_text_returns_stripped_text():
    tag = BeautifulSoup("<p>  text  </p>", "html.parser").p
    assert RezkaBase.get_text(tag) == "text"
