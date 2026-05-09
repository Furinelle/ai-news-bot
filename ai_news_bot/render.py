from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from .models import NewsItem


SECTION_ORDER = ("科技热点", "AI动态", "GitHub Trending")


def default_date_label() -> str:
    now = datetime.now()
    return f"{now.year}年{now.month}月{now.day}日"


def render_fallback_report(items: list[NewsItem], date_label: str | None = None) -> str:
    label = date_label or default_date_label()
    grouped: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        grouped[item.category or "科技热点"].append(item)

    lines = [
        "📡 Firefly · 每日科技/AI日报",
        label,
        "",
        "───",
    ]

    for section in SECTION_ORDER:
        section_items = grouped.get(section, [])
        if not section_items:
            continue
        heading = "🔥 今日科技新闻热点" if section == "科技热点" else section
        if section == "AI动态":
            heading = "🤖 AI动态 · 重要动态"
        if section == "GitHub Trending":
            heading = "📦 GitHub Trending 热门项目"
        lines.extend(["", heading, ""])
        for index, item in enumerate(section_items, start=1):
            summary = f" — {item.summary}" if item.summary else ""
            lines.append(f"{index}. {item.title}{summary}")
            lines.append(f"   来源：{item.source} {item.url}")

    lines.extend(["", "───", "由 AI News Bot 自动生成，重大信息请以原文来源为准。"])
    return "\n".join(lines).strip()
