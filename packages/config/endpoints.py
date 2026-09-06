"""Authoritative endpoint classification for offline provider configuration checks."""

from urllib.parse import urlsplit


def safe_endpoint_class(value: str) -> dict[str, str] | None:
    parsed = urlsplit(value)
    regions = {
        "api.openai.com": "global",
        "us.api.openai.com": "us",
        "eu.api.openai.com": "eu",
        "au.api.openai.com": "au",
        "ca.api.openai.com": "ca",
        "jp.api.openai.com": "jp",
        "in.api.openai.com": "in",
        "sg.api.openai.com": "sg",
        "kr.api.openai.com": "kr",
        "gb.api.openai.com": "gb",
        "ae.api.openai.com": "ae",
    }
    region = regions.get((parsed.hostname or "").lower())
    if (
        parsed.scheme != "https"
        or region is None
        or parsed.path.rstrip("/") != "/v1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    return {"endpoint_class": "official_openai", "region": region}
