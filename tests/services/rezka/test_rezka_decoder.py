import base64

import pytest

from app.services.rezka.rezka_decoder import StreamDecoder


def encode_data(s: str) -> str:
    return "xx" + base64.b64encode(s.encode()).decode()


def test_decode_returns_dict_correctly(monkeypatch):
    decoded_str = "[720p] https://example.com/720.mp4,[480p] https://example.com/480.mp4"
    encoded = encode_data(decoded_str)

    monkeypatch.setattr(StreamDecoder, "_decode_stream_base64", lambda x: decoded_str)

    result = StreamDecoder.decode(encoded)
    assert result == {
        "720p": "https://example.com/720.mp4",
        "480p": "https://example.com/480.mp4",
    }


def test_decode_skips_ultra_quality(monkeypatch):
    decoded_str = "[1080p Ultra] https://example.com/1080.mp4,[720p] https://example.com/720.mp4"
    encoded = encode_data(decoded_str)

    monkeypatch.setattr(StreamDecoder, "_decode_stream_base64", lambda x: decoded_str)

    result = StreamDecoder.decode(encoded)
    assert "1080p Ultra" not in result
    assert "720p" in result


def test_decode_raises_value_error_on_empty_input():
    with pytest.raises(ValueError):
        StreamDecoder.decode("")


def test_decode_raises_exception_on_invalid_base64():
    invalid_encoded = "invalid!!"
    with pytest.raises(Exception) as excinfo:
        StreamDecoder.decode(invalid_encoded)
    assert "Error during decoding" in str(excinfo.value)


def test_decode_stream_base64_removes_trash_and_separator():
    original = "data"
    encoded = base64.b64encode(original.encode()).decode()
    s = "xx" + encoded
    result = StreamDecoder._decode_stream_base64(s)
    assert result == "data"
