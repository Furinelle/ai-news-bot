from __future__ import annotations

from .dedupe import dedupe_items, normalize_url
from .models import INTEREST_CATEGORY, NewsItem


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

# 前三节仍按配额均衡；兴趣推荐节单独预留名额，避免冲掉新闻/Trending。
PRIMARY_SECTIONS = ("科技热点", "AI动态", "GitHub Trending")
SECTION_ORDER = (*PRIMARY_SECTIONS, INTEREST_CATEGORY)
DEFAULT_INTEREST_LIMIT = 8


DEFAULT_MAX_HN_PER_SECTION = 5


def score_item(item: NewsItem) -> float:
    text = f"{item.title} {item.summary}".casefold()
    keyword_score = sum(weight for word, weight in KEYWORD_WEIGHTS.items() if word in text)
    return item.score + keyword_score


def rank_items(items: list[NewsItem], limit: int) -> list[NewsItem]:
    return sorted(items, key=score_item, reverse=True)[:limit]


def _take_with_source_caps(
    items: list[NewsItem],
    limit: int,
    *,
    max_hn: int = DEFAULT_MAX_HN_PER_SECTION,
) -> list[NewsItem]:
    """同节内限制 Hacker News 占比，避免整节被 HN 刷满。"""
    if limit <= 0:
        return []
    ranked = rank_items(items, limit=len(items))
    selected: list[NewsItem] = []
    hn_count = 0
    for item in ranked:
        is_hn = item.source.casefold() == "hacker news"
        if is_hn and hn_count >= max_hn:
            continue
        selected.append(item)
        if is_hn:
            hn_count += 1
        if len(selected) >= limit:
            break
    return selected[:limit]


def select_report_items(
    items: list[NewsItem],
    limit: int,
    interest_limit: int = DEFAULT_INTEREST_LIMIT,
    max_hn_per_section: int = DEFAULT_MAX_HN_PER_SECTION,
) -> list[NewsItem]:
    if limit <= 0:
        return []

    interest_candidates = [item for item in items if item.category == INTEREST_CATEGORY]
    interest_quota = max(0, min(interest_limit, limit)) if interest_candidates else 0
    selected_interest = rank_items(interest_candidates, interest_quota) if interest_quota else []
    remaining_limit = limit - len(selected_interest)

    selected: list[NewsItem] = []
    selected_urls: set[str] = {normalize_url(item.url) for item in selected_interest}

    if remaining_limit > 0:
        per_section = max(1, remaining_limit // len(PRIMARY_SECTIONS))
        for section in PRIMARY_SECTIONS:
            section_items = [
                item
                for item in items
                if item.category == section and normalize_url(item.url) not in selected_urls
            ]
            picked = _take_with_source_caps(
                section_items,
                per_section,
                max_hn=max_hn_per_section if section in {"科技热点", "AI动态"} else 10**9,
            )
            for item in picked:
                selected.append(item)
                selected_urls.add(normalize_url(item.url))

        if len(selected) < remaining_limit:
            remainder = [
                item
                for item in items
                if item.category != INTEREST_CATEGORY and normalize_url(item.url) not in selected_urls
            ]
            for item in _take_with_source_caps(
                remainder,
                remaining_limit - len(selected),
                max_hn=max_hn_per_section,
            ):
                selected.append(item)
                selected_urls.add(normalize_url(item.url))

    # 兴趣节固定放在前三节之后
    ordered = selected[:remaining_limit] + selected_interest
    return ordered[:limit]


def select_report_items_with_fallback(
    primary_items: list[NewsItem],
    fallback_items: list[NewsItem],
    limit: int,
    no_fallback_categories: set[str] | None = None,
    interest_limit: int = DEFAULT_INTEREST_LIMIT,
    max_hn_per_section: int = DEFAULT_MAX_HN_PER_SECTION,
) -> list[NewsItem]:
    if limit <= 0:
        return []

    no_fallback_categories = no_fallback_categories or set()
    primary = select_report_items(
        dedupe_items(primary_items),
        limit=limit,
        interest_limit=interest_limit,
        max_hn_per_section=max_hn_per_section,
    )
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
        *select_report_items(
            fallback,
            limit=limit - len(primary),
            interest_limit=interest_limit,
            max_hn_per_section=max_hn_per_section,
        ),
    ][:limit]
