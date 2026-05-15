import base64
import re


class StreamDecoder:
    _STREAM_SEPARATOR = "//_//"
    _TRASH_LIST = [
        "$$#!!@#!@##",
        "^^^!@##!!##",
        "####^!!##!@@",
        "@@@@@!##!^^^",
        "$$!!@$$@^!@#$$@",
    ]
    _QUALITY_PATTERN = re.compile(r"^\[(\d+p(?:\s\w*)?)\]")

    @classmethod
    def _decode_stream_base64(cls, stream_encoded: str) -> str:
        stream_encoded = stream_encoded[2:]
        for _ in range(2):
            stream_encoded = stream_encoded.replace(cls._STREAM_SEPARATOR, "")
            for value in cls._TRASH_LIST:
                trash_b64 = base64.b64encode(value.encode()).decode()
                stream_encoded = stream_encoded.replace(trash_b64, "")
        return base64.b64decode(stream_encoded).decode()

    @classmethod
    def decode(cls, base64_encoded_stream: str) -> dict[str, str]:
        if not base64_encoded_stream:
            raise ValueError("base64_encoded_stream cannot be empty")

        try:

            decoded = cls._decode_stream_base64(base64_encoded_stream)
        except Exception as e:
            raise Exception(f"Error during decoding: {e}")

        streams: dict[str, str] = {}
        for part in decoded.split(","):
            match = cls._QUALITY_PATTERN.match(part)
            if not match:
                continue
            quality = match.group(1)
            if quality == "1080p Ultra":
                continue
            urls = [u.strip() for u in part[match.end() :].split(" or ")]
            mp4_url = next((u for u in urls if u.endswith(".mp4")), None)
            if mp4_url:
                streams[quality] = mp4_url
        return streams
