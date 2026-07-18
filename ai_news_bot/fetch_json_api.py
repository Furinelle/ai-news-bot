from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from .fetch_rss import clean_summary
from .models import NewsItem


def _dig(data: Any, path: str) -> Any:
    value = data
    for part in path.split("."):
        if not part:
            continue
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _first_string(data: dict[str, Any], fields: list[str]) -> str:
    for field in fields:
        value = _dig(data, field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def fetch_json_api(
    url: str,
    source: str,
    category: str = "科技热点",
    items_path: str = "results",
    title_fields: list[str] | None = None,
    url_fields: list[str] | None = None,
    summary_fields: list[str] | None = None,
    published_fields: list[str] | None = None,
    source_fields: list[str] | None = None,
    timeout_seconds: float = 20,
) -> list[NewsItem]:
    request = Request(url, headers={"User-Agent": "ai-news-bot/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)

    raw_items = _dig(payload, items_path) if items_path else payload
    if not isinstance(raw_items, list):
        return []

    title_fields = title_fields or ["title"]
    url_fields = url_fields or ["url", "link"]
    summary_fields = summary_fields or ["summary", "description"]
    published_fields = published_fields or ["published_at", "published", "updated_at", "updated"]
    source_fields = source_fields or ["source", "news_site"]

    items: list[NewsItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        title = _first_string(raw, title_fields)
        link = _first_string(raw, url_fields)
        if not title or not link:
            continue
        item_source = _first_string(raw, source_fields) or source
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=item_source,
                summary=clean_summary(_first_string(raw, summary_fields)),
                category=category,
                published_at=_first_string(raw, published_fields) or None,
            )
        )
    return items
