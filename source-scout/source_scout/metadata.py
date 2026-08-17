from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

TRACKING_PARAMS = {"fbclid", "gclid", "igsh", "igshid", "si", "feature", "app", "ref", "source"}


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.metadata: dict[str, str] = {}
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            content = values.get("content", "").strip()
            if key and content and key not in self.metadata:
                self.metadata[key] = content
        elif tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    def result(self) -> dict[str, str]:
        return {
            "title": self.metadata.get("og:title") or self.metadata.get("twitter:title") or " ".join(self._title_parts).strip(),
            "description": self.metadata.get("og:description") or self.metadata.get("description") or self.metadata.get("twitter:description") or "",
            "creator": self.metadata.get("author") or self.metadata.get("article:author") or "",
            "thumbnail_url": self.metadata.get("og:image") or self.metadata.get("twitter:image") or "",
        }


def canonicalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/") or "/", "", urlencode(query), ""))


def ensure_public_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("공개 http 또는 https URL만 사용할 수 있습니다.")
    if parsed.username or parsed.password:
        raise ValueError("인증 정보가 포함된 URL은 사용할 수 없습니다.")
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443)}
    except socket.gaierror as exc:
        raise ValueError("URL의 호스트를 확인할 수 없습니다.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError("내부망 또는 로컬 주소에는 접근할 수 없습니다.")


def fetch_metadata(value: str, timeout: float = 8.0) -> dict[str, str]:
    ensure_public_url(value)
    request = Request(
        value,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; SourceScout/0.3; +https://scout.jisiknarae.com)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        ensure_public_url(final_url)
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise ValueError("HTML 페이지가 아닙니다.")
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError("페이지가 분석 제한 크기를 초과했습니다.")
        charset = response.headers.get_content_charset() or "utf-8"
    parser = MetadataParser()
    parser.feed(raw.decode(charset, errors="replace"))
    return {**parser.result(), "url": canonicalize_url(final_url)}
