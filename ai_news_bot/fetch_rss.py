from __future__ import annotations

import html
import re

from .models import NewsItem


def clean_summary(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", value)
    unescaped = html.unescape(no_tags).replace("…", "...")
    return re.sub(r"\s+", " ", unescaped).strip()


def fetch_rss_feed(url: str, source: str, category: str = "科技热点") -> list[NewsItem]:
    import feedparser

    feed = feedparser.parse(url)
    items: list[NewsItem] = []
    for entry in feed.entries:
        title = str(getattr(entry, "title", "")).strip()
        link = str(getattr(entry, "link", "")).strip()
        if not title or not link:
            continue
        summary = clean_summary(str(getattr(entry, "summary", "")).strip())
        published = str(getattr(entry, "published", "") or getattr(entry, "updated", "")).strip()
        items.append(
            NewsItem(
                title=title,
                url=link,
                source=source,
                summary=summary,
                category=category,
                published_at=published or None,
            )
        )
    return items
