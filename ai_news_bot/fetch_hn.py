from __future__ import annotations

from typing import Any

from .models import NewsItem


HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"

AI_TITLE_KEYWORDS = (
    "ai",
    "llm",
    "gpt",
    "claude",
    "openai",
    "anthropic",
    "gemini",
    "deepseek",
    "agent",
    "transformer",
    "diffusion",
    "机器学习",
    "大模型",
    "人工智能",
)


def _classify_hn(title: str) -> str:
    text = title.casefold()
    if any(keyword in text for keyword in AI_TITLE_KEYWORDS):
        return "AI动态"
    return "科技热点"


def fetch_hacker_news(
    limit: int = 20,
    *,
    min_score: int = 40,
    fetch_pool: int | None = None,
) -> list[NewsItem]:
    """拉取 HN。按分数过滤，并按标题关键词分流到 AI/科技。"""
    import httpx

    pool = fetch_pool or max(limit * 3, 60)
    with httpx.Client(timeout=30) as client:
        ids_response = client.get(HN_TOP_URL)
        ids_response.raise_for_status()
        item_ids = ids_response.json()[:pool]

        items: list[NewsItem] = []
        for item_id in item_ids:
            if len(items) >= limit:
                break
            response = client.get(HN_ITEM_URL.format(item_id=item_id))
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            if not isinstance(data, dict):
                continue
            if data.get("type") and data.get("type") != "story":
                continue
            title = str(data.get("title", "")).strip()
            if not title:
                continue
            score = float(data.get("score") or 0)
            if score < min_score:
                continue
            url = str(data.get("url") or f"https://news.ycombinator.com/item?id={item_id}")
            items.append(
                NewsItem(
                    title=title,
                    url=url,
                    source="Hacker News",
                    category=_classify_hn(title),
                    score=score,
                    summary=f"HN score {int(score)}",
                    tags=[f"hn_score:{int(score)}"],
                )
            )
        return items
