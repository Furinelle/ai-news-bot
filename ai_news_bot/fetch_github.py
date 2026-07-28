from __future__ import annotations

import re
import time
from typing import Any

from .models import NewsItem


def fetch_github_trending(
    language: str = "",
    since: str = "daily",
    limit: int = 10,
    *,
    retries: int = 3,
    client: Any | None = None,
) -> list[NewsItem]:
    import httpx
    from bs4 import BeautifulSoup

    path = f"/trending/{language.strip()}" if language.strip() else "/trending"
    url = f"https://github.com{path}?since={since}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; ai-news-bot/1.5; +https://github.com/Furinelle/ai-news-bot)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=30.0)

    last_error: Exception | None = None
    try:
        for attempt in range(max(1, retries)):
            try:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                return _parse_trending_html(response.text, limit=limit)
            except Exception as exc:  # network / HTTP / parse
                last_error = exc
                if attempt + 1 < retries:
                    time.sleep(0.6 * (attempt + 1))
        if last_error is not None:
            raise last_error
        return []
    finally:
        if owns_client:
            client.close()


def _parse_trending_html(html: str, limit: int) -> list[NewsItem]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    items: list[NewsItem] = []
    for article in soup.select("article.Box-row")[:limit]:
        title_node = article.select_one("h2 a")
        if title_node is None:
            continue
        repo_path = " ".join(title_node.get_text(" ", strip=True).split()).replace(" / ", "/")
        href = str(title_node.get("href", "")).strip()
        repo_url = "https://github.com" + href if href.startswith("/") else href
        desc_node = article.select_one("p")
        summary = desc_node.get_text(" ", strip=True) if desc_node else ""

        total_stars = _parse_count(article.select_one('a[href$="/stargazers"]'))
        today_stars = _parse_today_stars(article)
        # 优先用「今日 star」排序；没有则退回总 star 的对数缩放
        score = float(today_stars) if today_stars > 0 else max(total_stars / 1000.0, 0.1)

        tags: list[str] = []
        if today_stars > 0:
            tags.append(f"stars_today:{today_stars}")
        if total_stars > 0:
            tags.append(f"stars_total:{int(total_stars)}")

        if today_stars > 0:
            summary = f"{summary} · +{today_stars}★ today".strip(" ·")

        items.append(
            NewsItem(
                title=repo_path,
                url=repo_url,
                source="GitHub Trending",
                summary=summary,
                category="GitHub Trending",
                score=score,
                tags=tags,
            )
        )
    return items


def _parse_count(node: Any) -> float:
    if node is None:
        return 0.0
    text = node.get_text(strip=True).replace(",", "")
    if text.isdigit():
        return float(text)
    return 0.0


def _parse_today_stars(article: Any) -> int:
    """解析 Trending 页「N stars today/this week/this month」。"""
    text = article.get_text(" ", strip=True)
    match = re.search(
        r"([\d,]+)\s+stars?\s+(today|this week|this month)",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        # 备用：部分页面结构在 span 里
        for span in article.select("span"):
            span_text = span.get_text(" ", strip=True)
            m = re.search(r"([\d,]+)\s+stars?", span_text, flags=re.IGNORECASE)
            if m and re.search(r"today|this week|this month", span_text, re.I):
                return int(m.group(1).replace(",", ""))
        return 0
    return int(match.group(1).replace(",", ""))
