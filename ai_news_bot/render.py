from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import re

from .models import NewsItem


SECTION_ORDER = ("科技热点", "AI动态", "GitHub Trending")
SECTION_HEADINGS = {
    "科技热点": "## 🔥 科技热点",
    "AI动态": "## 🤖 AI动态",
    "GitHub Trending": "## 📦 GitHub Trending",
}


def strip_markdown_emphasis(text: str) -> str:
    return text.replace("**", "").replace("__", "")


def default_date_label() -> str:
    now = datetime.now()
    return f"{now.year}年{now.month}月{now.day}日"


def _is_item_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return False
    if re.fullmatch(r"[-─=*]{3,}", stripped):
        return False
    if line[0] in (" ", "\t"):
        return False
    if stripped.startswith(("（", "(", ">")):
        return False
    if re.match(r"^\d{4}年", stripped):
        return False
    return True


def _strip_item_prefix(line: str) -> str:
    stripped = line.strip()
    for pattern in (
        r"^\d+\.\s+(.*)",
        r"^\d+[、)]\s*(.*)",
        r"^[-•]\s+(.*)",
    ):
        match = re.match(pattern, stripped, re.DOTALL)
        if match:
            return match.group(1)
    return stripped


def _canonical_section_heading(line: str) -> str | None:
    stripped = line.strip()
    stripped = re.sub(r"^#+\s*", "", stripped)
    stripped = re.sub(r"^(一|二|三|[0-9]+)[、.)]\s*", "", stripped)
    stripped = stripped.replace("🔥", "").replace("🤖", "").replace("📦", "").strip()
    stripped = stripped.rstrip(":：").strip()
    normalized = re.sub(r"\s+", " ", stripped).casefold()
    if normalized == "科技热点":
        return SECTION_HEADINGS["科技热点"]
    if normalized in {"ai动态", "ai 动态"}:
        return SECTION_HEADINGS["AI动态"]
    if normalized == "github trending":
        return SECTION_HEADINGS["GitHub Trending"]
    return None


def fix_numbering(report: str) -> str:
    """Normalize section items to Markdown ordered lists."""
    result: list[str] = []
    in_section = False
    counter = 0

    for line in report.splitlines():
        if re.fullmatch(r"[-─=*]{3,}", line.strip()):
            in_section = False
            result.append(line)
            continue
        section_heading = _canonical_section_heading(line)
        if section_heading:
            in_section = True
            counter = 0
            result.append(section_heading)
            continue
        if in_section and _is_item_line(line):
            counter += 1
            result.append(f"{counter}. {_strip_item_prefix(line)}")
            continue
        result.append(line)

    return "\n".join(result)


def render_fallback_report(items: list[NewsItem], date_label: str | None = None) -> str:
    label = date_label or default_date_label()
    grouped: dict[str, list[NewsItem]] = defaultdict(list)
    for item in items:
        grouped[item.category or "科技热点"].append(item)

    lines = [
        "# 📡 Furina · 每日科技/AI日报",
        label,
        "",
        "---",
    ]

    for section in SECTION_ORDER:
        section_items = grouped.get(section, [])
        if not section_items:
            continue
        heading = SECTION_HEADINGS[section]
        lines.extend(["", heading, ""])
        for index, item in enumerate(section_items, start=1):
            summary = f" — {item.summary}" if item.summary else ""
            if section == "GitHub Trending":
                lines.append(f"{index}. [{item.title}]({item.url}){summary}")
            else:
                lines.append(f"{index}. {item.title}{summary}（来源：{item.source}）")

    lines.extend(["", "---", "由 AI News Bot 自动生成，重大信息请以原文来源为准。"])
    return fix_numbering(strip_markdown_emphasis("\n".join(lines).strip()))
