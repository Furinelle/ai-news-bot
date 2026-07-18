from __future__ import annotations

from .dedupe import dedupe_items, normalize_url
from .models import NewsItem


KEYWORD_WEIGHTS = {
    "openai": 5,
    "anthropic": 5,
    "google": 3,
    "microsoft": 3,
    "apple": 3,
    "ai": 4,
    "人工智能": 4,
    "大模型": 4,
    "芯片": 3,
    "github": 3,
    "机器人": 3,
}

SECTION_ORDER = ("科技热点", "AI动态", "GitHub Trending")


def score_item(item: NewsItem) -> float:
    text = f"{item.title} {item.summary}".casefold()
    keyword_score = sum(weight for word, weight in KEYWORD_WEIGHTS.items() if word in text)
    return item.score + keyword_score


def rank_items(items: list[NewsItem], limit: int) -> list[NewsItem]:
    return sorted(items, key=score_item, reverse=True)[:limit]


def select_report_items(items: list[NewsItem], limit: int) -> list[NewsItem]:
    if limit <= 0:
        return []

    per_section = max(1, limit // len(SECTION_ORDER))
    selected: list[NewsItem] = []
    selected_urls: set[str] = set()

    for section in SECTION_ORDER:
        section_items = [item for item in items if item.category == section]
        for item in rank_items(section_items, per_section):
            selected.append(item)
            selected_urls.add(normalize_url(item.url))

    if len(selected) < limit:
        remainder = [item for item in items if normalize_url(item.url) not in selected_urls]
        selected.extend(rank_items(remainder, limit - len(selected)))

    return selected[:limit]


def select_report_items_with_fallback(
    primary_items: list[NewsItem],
    fallback_items: list[NewsItem],
    limit: int,
    no_fallback_categories: set[str] | None = None,
) -> list[NewsItem]:
    if limit <= 0:
        return []

    no_fallback_categories = no_fallback_categories or set()
    primary = select_report_items(dedupe_items(primary_items), limit=limit)
    if len(primary) >= limit:
        return primary

    selected_urls = {normalize_url(item.url) for item in primary}
    allowed_fallback = [
        item
        for item in fallback_items
        if item.category not in no_fallback_categories
        and normalize_url(item.url) not in selected_urls
    ]
    combined = dedupe_items([*primary, *allowed_fallback])
    fallback = combined[len(primary) :]
    return [
        *primary,
        *select_report_items(fallback, limit=limit - len(primary)),
    ][:limit]
