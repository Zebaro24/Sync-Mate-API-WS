import pytest

from tests.client import client

test_titles = [
    "a",
    "Рик и Морти",
    "Проверка",
]

test_ids = [
    2136,
    55648,
    17292,
    81398,
]

test_urls = [
    "https://rezka.ag/cartoons/adventures/17292-rikki-tikki-tavi-1965.html",
    "https://rezka.ag/films/documentary/55648-god-2023.html",
    "https://rezka.ag/films/drama/6089-riki-2009.html",
    "https://rezka.ag/films/fiction/81398-holodnoe-hranilische-2026.html",
    "https://rezka.ag/cartoons/comedy/2136-rik-i-morti-2013-latest.html",
]

test_movies = [
    {"movie_id": 17292, "translator_id": 110},
    {"movie_id": 55648, "translator_id": 110},
]


test_series = [
    {"series_id": 2136, "translator_id": 66, "season": 4, "episode": 3},
    {"series_id": 81473, "translator_id": 35, "season": 1, "episode": 2},
    {"series_id": 81086, "translator_id": 35},
]


@pytest.mark.parametrize("test_title", test_titles)
def test_search(test_title):
    response = client.get("/api/rezka/quick_search", params={"movie_title": test_title})
    assert response.status_code == 200

    response = client.get("/api/rezka/search", params={"movie_title": test_title})
    assert response.status_code == 200


@pytest.mark.parametrize("test_id", test_ids)
def test_quick_info_movie(test_id):
    response = client.get("/api/rezka/quick_info_movie", params={"movie_id": test_id})
    assert response.status_code == 200


@pytest.mark.parametrize("test_url", test_urls)
def test_info_movie(test_url):
    response = client.get("/api/rezka/info_movie", params={"movie_url": test_url})
    assert response.status_code == 200


@pytest.mark.parametrize("test_movie", test_movies)
def test_movie_source(test_movie):
    response = client.get("/api/rezka/movie_source", params=test_movie)
    assert response.status_code == 200


@pytest.mark.parametrize("test_series_elem", test_series)
def test_series_source(test_series_elem):
    response = client.get("/api/rezka/series_source", params=test_series_elem)
    assert response.status_code == 200
