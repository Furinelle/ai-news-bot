from __future__ import annotations

import re
from collections import defaultdict

from .models import INTEREST_CATEGORY, NewsItem
from .render import SECTION_HEADINGS, fix_numbering, render_fallback_report

GITHUB_ITEM_RE = re.compile(
    r"^\d+\.\s+\[([^\]]+)\]\((https://github\.com/[^)\s]+)\)\s*(.*)$"
)
FLUFF_PATTERNS = (
    re.compile(r"具体功能待探索"),
    re.compile(r"值得持续关注"),
    re.compile(r"值得关注$"),
    re.compile(r"功能尚不明确"),
    re.compile(r"详情有限"),
)


def strip_trailing_source_for_github(description: str) -> str:
    """去掉误加的（来源：…）尾巴。"""
    text = description.strip()
    text = re.sub(r"（来源：\[[^\]]+\]\([^)]+\)）\s*$", "", text).strip()
    text = re.sub(r"\(来源：\[[^\]]+\]\([^)]+\)\)\s*$", "", text).strip()
    return text


def is_fluff_description(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) < 8:
        return True
    return any(pattern.search(stripped) for pattern in FLUFF_PATTERNS)


def sanitize_github_sections(report: str, selected: list[NewsItem]) -> str:
    """
    校正 GitHub Trending / 你可能感兴趣 两节：
    - 强制 [repo](url) 开头
    - 去掉错误的「来源」尾巴
    - 丢掉空话描述；必要时用候选摘要回填整节
    """
    by_category: dict[str, list[NewsItem]] = defaultdict(list)
    for item in selected:
        if item.category in {"GitHub Trending", INTEREST_CATEGORY}:
            by_category[item.category].append(item)

    lines = report.splitlines()
    result: list[str] = []
    current: str | None = None
    section_ok: dict[str, bool] = {
        "GitHub Trending": False,
        INTEREST_CATEGORY: False,
    }
    buffered: dict[str, list[str]] = {
        "GitHub Trending": [],
        INTEREST_CATEGORY: [],
    }

    def flush(section: str | None) -> None:
        if section not in buffered:
            return
        items = buffered[section]
        if not items:
            # 空节：用候选回填
            fallback = _fallback_section_lines(by_category.get(section, []), section)
            result.extend(fallback)
            section_ok[section] = bool(fallback)
            return
        cleaned: list[str] = []
        for index, line in enumerate(items, start=1):
            match = GITHUB_ITEM_RE.match(line.strip())
            if not match:
                continue
            title, url, desc = match.groups()
            desc = strip_trailing_source_for_github(desc)
            if is_fluff_description(desc):
                # 尝试用候选 summary 替换
                desc = _lookup_summary(by_category.get(section, []), url, title) or ""
            if is_fluff_description(desc):
                cleaned.append(f"{index}. [{title}]({url})")
            else:
                cleaned.append(f"{index}. [{title}]({url}) {desc}".rstrip())
        if not cleaned:
            cleaned = _fallback_section_lines(by_category.get(section, []), section)
        # 重编号
        renumbered = []
        for index, line in enumerate(cleaned, start=1):
            body = re.sub(r"^\d+\.\s*", "", line.strip())
            renumbered.append(f"{index}. {body}")
        result.extend(renumbered)
        section_ok[section] = bool(renumbered)

    for line in lines:
        heading = _match_github_heading(line)
        if heading:
            flush(current)
            current = heading
            buffered[current] = []
            result.append(SECTION_HEADINGS[heading])
            continue
        if line.startswith("## "):
            flush(current)
            current = None
            result.append(line)
            continue
        if current is not None:
            if re.match(r"^\d+\.\s+", line.strip()) or line.strip().startswith("["):
                buffered[current].append(line)
            elif not line.strip():
                continue
            else:
                # 节内杂讯丢弃
                continue
        else:
            result.append(line)

    flush(current)
    return fix_numbering("\n".join(result).strip())


def _match_github_heading(line: str) -> str | None:
    stripped = re.sub(r"^#+\s*", "", line.strip())
    stripped = stripped.replace("📦", "").replace("⭐", "").strip()
    normalized = re.sub(r"\s+", " ", stripped).casefold()
    if normalized == "github trending":
        return "GitHub Trending"
    if normalized in {"你可能感兴趣", "可能感兴趣"}:
        return INTEREST_CATEGORY
    return None


def _lookup_summary(items: list[NewsItem], url: str, title: str) -> str:
    url_l = url.rstrip("/").casefold()
    title_l = title.casefold()
    for item in items:
        if item.url.rstrip("/").casefold() == url_l or item.title.casefold() == title_l:
            return item.summary.strip()
    return ""


def _fallback_section_lines(items: list[NewsItem], section: str) -> list[str]:
    if not items:
        return []
    # 复用 fallback 渲染再抽出列表行
    md = render_fallback_report(items, date_label="DATE")
    lines: list[str] = []
    in_section = False
    for line in md.splitlines():
        if line.strip() == SECTION_HEADINGS.get(section):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break
        if in_section and re.match(r"^\d+\.\s+", line.strip()):
            lines.append(line.strip())
    return lines


def enforce_section_caps(report: str, *, trending_max: int = 15, interest_max: int = 8) -> str:
    """防止 LLM 某节爆量。"""
    lines = report.splitlines()
    result: list[str] = []
    current: str | None = None
    count = 0
    for line in lines:
        heading = _match_github_heading(line)
        if line.startswith("## "):
            current = heading
            count = 0
            result.append(line if not heading else SECTION_HEADINGS[heading])
            continue
        if current and re.match(r"^\d+\.\s+", line.strip()):
            limit = trending_max if current == "GitHub Trending" else interest_max
            count += 1
            if count <= limit:
                result.append(line)
            continue
        result.append(line)
    return "\n".join(result)
