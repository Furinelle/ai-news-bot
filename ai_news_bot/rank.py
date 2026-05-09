from __future__ import annotations

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


def score_item(item: NewsItem) -> float:
    text = f"{item.title} {item.summary}".casefold()
    keyword_score = sum(weight for word, weight in KEYWORD_WEIGHTS.items() if word in text)
    return item.score + keyword_score


def rank_items(items: list[NewsItem], limit: int) -> list[NewsItem]:
    return sorted(items, key=score_item, reverse=True)[:limit]


def select_report_items(items: list[NewsItem], limit: int) -> list[NewsItem]:
    if limit <= 0:
        return []

    sections = ("科技热点", "AI动态", "GitHub Trending")
    per_section = max(1, limit // len(sections))
    selected: list[NewsItem] = []
    selected_urls: set[str] = set()

    for section in sections:
        section_items = [item for item in items if item.category == section]
        for item in rank_items(section_items, per_section):
            selected.append(item)
            selected_urls.add(item.url)

    if len(selected) < limit:
        remainder = [item for item in items if item.url not in selected_urls]
        selected.extend(rank_items(remainder, limit - len(selected)))

    return selected[:limit]
