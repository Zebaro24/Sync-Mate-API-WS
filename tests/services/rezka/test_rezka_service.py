import pytest
from bs4 import BeautifulSoup

from app.services.rezka.rezka_service import RezkaService

HTML_QUICK_SEARCH = """
<ul>
    <li><a href="/12345-rik.html">
        <span class="enty">Рик и Морти</span> (Rick and Morty)
        <i class="hd-tooltip">9.5</i>
    </a></li>
</ul>
"""

HTML_QUICK_INFO = """
<div class="b-content__catlabel">Cartoon</div>
<div class="b-content__bubble_title">Рик и Морти</div>
<div class="b-content__bubble_rating">9.8</div>
<div class="b-content__bubble_text">Описание сериала</div>
<div class="b-content__bubble_text">
    <a>Комедия</a>
    <a>Фантастика</a>
</div>
"""

HTML_SEARCH = """
<div class="b-content__inline_item" data-id="777" data-url="https://rezka.ag/cartoons/777.html">
  <div class="b-content__inline_item-link">
    <a>Рик и Морти</a>
    <div>Описание</div>
  </div>
  <span class="cat">Мультфильм</span>
  <img src="poster.jpg"/>
</div>
"""

HTML_INFO = """
<div class="b-post__title">Рик и Морти</div>
<div class="b-post__origtitle">Rick and Morty</div>
<a class="b-topnav__item-link active_section">Cartoon</a>
<div class="b-post__description_text">Описание сериала</div>
<script>sof.tv.initCDNMoviesEvents(12345, 678, 'abc')</script>
<span class="b-post__info_rates imdb"><span>9.0</span></span>
<span class="b-post__info_rates kp"><span>8.9</span></span>
<span itemprop="genre">Фантастика</span>
<span itemprop="genre">Комедия</span>
<li class="b-translator__item" data-translator_id="1">Озвучка 1</li>
"""


@pytest.fixture
def service():
    return RezkaService()


def test_quick_search_parses_correctly(service, mocker):
    soup = BeautifulSoup(HTML_QUICK_SEARCH, "html.parser")
    mocker.patch.object(service, "post", return_value=soup)

    result = service.quick_search("рик")
    assert len(result) == 1
    item = result[0]
    assert item.id == 12345
    assert item.title == "Рик и Морти"
    assert item.alter_title == "(Rick and Morty)"
    assert item.rating == "9.5"
    assert item.url == "/12345-rik.html"


def test_quick_info_movie_parses_correctly(service, mocker):
    soup = BeautifulSoup(HTML_QUICK_INFO, "html.parser")
    mocker.patch.object(service, "post", return_value=soup)

    info = service.quick_info_movie(1)
    assert info.id == 1
    assert info.title == "Рик и Морти"
    assert "Комедия" in info.genres
    assert info.rating == "9.8"


def test_search_parses_results(service, mocker):
    soup = BeautifulSoup(HTML_SEARCH, "html.parser")
    mocker.patch.object(service, "get", return_value=soup)

    results = service.search("рик")
    assert len(results) == 1
    item = results[0]
    assert item.id == 777
    assert item.title == "Рик и Морти"
    assert item.category == "Мультфильм"
    assert item.caption == "Описание"
    assert item.image == "poster.jpg"
    assert item.url.startswith("https://rezka.ag")


def test_info_movie_parses_all_fields(service, mocker):
    soup = BeautifulSoup(HTML_INFO, "html.parser")
    mocker.patch.object(service, "get", return_value=soup)

    info = service.info_movie("https://rezka.ag/cartoons/12345-rik.html")
    assert info.id == 12345
    assert info.title == "Рик и Морти"
    assert info.alter_title == "Rick and Morty"
    assert info.category == "Cartoon"
    assert "Фантастика" in info.genres
    assert info.rating["imdb"] == "9.0"
    assert info.translators[1] == "Озвучка 1"
    assert info.content_type == "movie"
