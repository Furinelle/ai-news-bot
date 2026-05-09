from __future__ import annotations

from .models import NewsItem


def fetch_github_trending(language: str = "", since: str = "daily", limit: int = 10) -> list[NewsItem]:
    import httpx
    from bs4 import BeautifulSoup

    path = f"/trending/{language.strip()}" if language.strip() else "/trending"
    url = f"https://github.com{path}?since={since}"
    response = httpx.get(url, timeout=30, headers={"User-Agent": "ai-news-bot/0.1"})
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    items: list[NewsItem] = []
    for article in soup.select("article.Box-row")[:limit]:
        title_node = article.select_one("h2 a")
        if title_node is None:
            continue
        repo_path = " ".join(title_node.get_text(" ", strip=True).split()).replace(" / ", "/")
        repo_url = "https://github.com" + str(title_node.get("href", "")).strip()
        desc_node = article.select_one("p")
        summary = desc_node.get_text(" ", strip=True) if desc_node else ""
        star_node = article.select_one('a[href$="/stargazers"]')
        stars = 0.0
        if star_node:
            star_text = star_node.get_text(strip=True).replace(",", "")
            if star_text.isdigit():
                stars = float(star_text)
        items.append(
            NewsItem(
                title=repo_path,
                url=repo_url,
                source="GitHub Trending",
                summary=summary,
                category="GitHub Trending",
                score=stars,
            )
        )
    return items

