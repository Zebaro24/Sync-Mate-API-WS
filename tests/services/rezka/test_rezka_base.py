from bs4 import BeautifulSoup

from app.services.rezka.rezka_base import RezkaBase


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
    assert result.p.text == "Hello"


def test_get_calls_httpx_get(mocker):
    mock_get = mocker.patch("app.services.rezka.rezka_base.get")
    mock_get.return_value = mocker.MagicMock(text="<html></html>")

    base = RezkaBase()
    mock_parse = mocker.patch.object(base, "_parse_response", return_value="parsed")

    result = base.get("/page", params={"q": 1})

    mock_get.assert_called_once()
    mock_parse.assert_called_once()
    assert result == "parsed"


def test_post_calls_httpx_post(mocker):
    mock_post = mocker.patch("app.services.rezka.rezka_base.post")
    mock_post.return_value = mocker.MagicMock(text="<html></html>")

    base = RezkaBase()
    mock_parse = mocker.patch.object(base, "_parse_response", return_value="parsed")

    result = base.post("/submit", data={"a": 1})

    mock_post.assert_called_once()
    mock_parse.assert_called_once()
    assert result == "parsed"


def test_get_text_returns_none_if_tag_none():
    assert RezkaBase.get_text(None) is None


def test_get_text_returns_stripped_text():
    tag = BeautifulSoup("<p>  text  </p>", "html.parser").p
    assert RezkaBase.get_text(tag) == "text"
