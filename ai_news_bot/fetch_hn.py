from __future__ import annotations

from typing import Any

from .models import NewsItem


HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"


def fetch_hacker_news(limit: int = 20) -> list[NewsItem]:
    import httpx

    with httpx.Client(timeout=30) as client:
        ids_response = client.get(HN_TOP_URL)
        ids_response.raise_for_status()
        item_ids = ids_response.json()[:limit]

        items: list[NewsItem] = []
        for item_id in item_ids:
            response = client.get(HN_ITEM_URL.format(item_id=item_id))
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            title = str(data.get("title", "")).strip()
            url = str(data.get("url") or f"https://news.ycombinator.com/item?id={item_id}")
            if title:
                items.append(
                    NewsItem(
                        title=title,
                        url=url,
                        source="Hacker News",
                        category="科技热点",
                        score=float(data.get("score", 0)),
                    )
                )
        return items

