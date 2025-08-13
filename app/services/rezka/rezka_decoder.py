import base64
import re


class StreamDecoder:
    stream_separator = "//_//"
    trash_list = [
        "$$#!!@#!@##",
        "^^^!@##!!##",
        "####^!!##!@@",
        "@@@@@!##!^^^",
        "$$!!@$$@^!@#$$@",
    ]

    @classmethod
    def _decode_stream_base64(cls, stream_encoded: str) -> str:
        stream_encoded = stream_encoded[2:]

        for _ in range(2):
            stream_encoded = stream_encoded.replace(cls.stream_separator, "")
            for value in cls.trash_list:
                trash_b64 = base64.b64encode(value.encode()).decode()
                stream_encoded = stream_encoded.replace(trash_b64, "")
        return base64.b64decode(stream_encoded).decode()

    @classmethod
    def decode(cls, base64_encoded_stream_original: str):
        if not base64_encoded_stream_original:
            raise ValueError("base64_encoded_stream_original cannot be None or empty")

        try:
            decoded = cls._decode_stream_base64(base64_encoded_stream_original)
        except Exception as e:
            raise Exception(f"Error during decoding: {e}")

        streams = {}
        quality_pattern = re.compile(r"^\[(\d+p(?:\s\w*)?)\]")

        for part in decoded.split(","):
            match = quality_pattern.match(part)
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
