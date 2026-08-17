from __future__ import annotations

import xml.etree.ElementTree as ET
from urllib.request import Request, urlopen

from .metadata import canonicalize_url, ensure_public_url


def _text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _first(element: ET.Element, *paths: str) -> ET.Element | None:
    for path in paths:
        found = element.find(path)
        if found is not None:
            return found
    return None


def parse_feed(data: bytes, limit: int = 25) -> list[dict[str, str]]:
    root = ET.fromstring(data)
    entries: list[dict[str, str]] = []
    if root.tag.lower().endswith("rss") or root.find("channel") is not None:
        for item in root.findall("./channel/item")[:limit]:
            entries.append({
                "title": _text(item.find("title")) or "피드 후보",
                "url": _text(item.find("link")),
                "description": _text(item.find("description")),
                "creator": _text(item.find("author")),
            })
    else:
        namespace = "{http://www.w3.org/2005/Atom}"
        atom_entries = root.findall(f"{namespace}entry") or root.findall("entry")
        for entry in atom_entries[:limit]:
            link = _first(entry, f"{namespace}link", "link")
            author = _first(entry, f"{namespace}author/{namespace}name", "author/name")
            entries.append({
                "title": _text(_first(entry, f"{namespace}title", "title")) or "피드 후보",
                "url": (link.get("href", "") if link is not None else "").strip(),
                "description": _text(_first(entry, f"{namespace}summary", "summary", f"{namespace}content", "content")),
                "creator": _text(author),
            })
    return [entry for entry in entries if entry["url"]]


def fetch_feed(feed_url: str, timeout: float = 10.0) -> list[dict[str, str]]:
    ensure_public_url(feed_url)
    request = Request(feed_url, headers={"User-Agent": "SourceScout/0.4 (+https://scout.jisiknarae.com)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml"})
    with urlopen(request, timeout=timeout) as response:
        ensure_public_url(response.geturl())
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        raise ValueError("피드가 분석 제한 크기를 초과했습니다.")
    entries = parse_feed(data)
    for entry in entries:
        entry["url"] = canonicalize_url(entry["url"])
    return entries
