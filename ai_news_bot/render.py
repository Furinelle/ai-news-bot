from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import html
import re
from zoneinfo import ZoneInfo

from .models import NewsItem


SECTION_ORDER = ("科技热点", "AI动态", "GitHub Trending", "你可能感兴趣")
SECTION_HEADINGS = {
    "科技热点": "## 🔥 科技热点",
    "AI动态": "## 🤖 AI动态",
    "GitHub Trending": "## 📦 GitHub Trending",
    "你可能感兴趣": "## ⭐ 你可能感兴趣",
}
GITHUB_LINK_SECTIONS = {"GitHub Trending", "你可能感兴趣"}
REPORT_TITLE = "Furina · 每周科技/AI周报"
REPORT_HEADING = f"# 📡 {REPORT_TITLE}"
# 周报覆盖天数（含生成日）
WEEKLY_LOOKBACK_DAYS = 7


def strip_markdown_emphasis(text: str) -> str:
    return text.replace("**", "").replace("__", "")


def week_window(report_date: date | None = None, lookback_days: int = WEEKLY_LOOKBACK_DAYS) -> tuple[date, date]:
    end = report_date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = end - timedelta(days=max(lookback_days, 1) - 1)
    return start, end


def default_date_label(report_date: date | None = None, lookback_days: int = WEEKLY_LOOKBACK_DAYS) -> str:
    """周报日期区间，如 2026年7月25日–7月31日。"""
    start, end = week_window(report_date, lookback_days=lookback_days)
    if start == end:
        return f"{end.year}年{end.month}月{end.day}日"
    if start.year == end.year and start.month == end.month:
        return f"{start.year}年{start.month}月{start.day}日–{end.day}日"
    if start.year == end.year:
        return f"{start.year}年{start.month}月{start.day}日–{end.month}月{end.day}日"
    return f"{start.year}年{start.month}月{start.day}日–{end.year}年{end.month}月{end.day}日"


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
    stripped = (
        stripped.replace("🔥", "")
        .replace("🤖", "")
        .replace("📦", "")
        .replace("⭐", "")
        .strip()
    )
    stripped = stripped.rstrip(":：").strip()
    normalized = re.sub(r"\s+", " ", stripped).casefold()
    if normalized == "科技热点":
        return SECTION_HEADINGS["科技热点"]
    if normalized in {"ai动态", "ai 动态"}:
        return SECTION_HEADINGS["AI动态"]
    if normalized == "github trending":
        return SECTION_HEADINGS["GitHub Trending"]
    if normalized in {"你可能感兴趣", "可能感兴趣", "github 兴趣推荐", "兴趣推荐"}:
        return SECTION_HEADINGS["你可能感兴趣"]
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
        REPORT_HEADING,
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
            if section in GITHUB_LINK_SECTIONS:
                lines.append(f"{index}. [{item.title}]({item.url}){summary}")
            else:
                lines.append(f"{index}. {item.title}{summary}（来源：[{item.source}]({item.url})）")

    lines.extend(["", "---", "由 AI News Bot 自动生成，重大信息请以原文来源为准。"])
    return fix_numbering(strip_markdown_emphasis("\n".join(lines).strip()))


def _render_inline_markdown(text: str) -> str:
    escaped = html.escape(text, quote=True)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2" rel="noopener noreferrer">\1</a>',
        escaped,
    )
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def render_html_report(markdown: str, title: str = REPORT_TITLE) -> str:
    lines = markdown.splitlines()
    intro: list[str] = []
    sections: list[dict[str, object]] = []
    in_list = False

    def target() -> list[str]:
        if sections:
            return sections[-1]["content"]  # type: ignore[return-value]
        return intro

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            target().append("</ol>")
            in_list = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if re.fullmatch(r"[-─=*]{3,}", line):
            close_list()
            if not sections:
                intro.append("<hr>")
            continue
        if line.startswith("# "):
            close_list()
            intro.append(f"<h1>{_render_inline_markdown(line[2:].strip())}</h1>")
            continue
        if line.startswith("## "):
            close_list()
            title_text = line[3:].strip()
            sections.append({"title": title_text, "content": []})
            continue
        match = re.match(r"^\d+\.\s+(.*)", line)
        if match:
            if not in_list:
                target().append("<ol>")
                in_list = True
            target().append(f"<li>{_render_inline_markdown(match.group(1))}</li>")
            continue
        close_list()
        target().append(f"<p>{_render_inline_markdown(line)}</p>")

    close_list()
    html_title = html.escape(title, quote=True)
    intro_html = "\n".join(intro)
    if sections:
        tab_buttons = []
        tab_panels = []
        for index, section in enumerate(sections):
            panel_id = f"section-{index}"
            selected = "true" if index == 0 else "false"
            active_class = " is-active" if index == 0 else ""
            hidden = "" if index == 0 else " hidden"
            section_title = str(section["title"])
            tab_buttons.append(
                f'<button class="tab-button{active_class}" type="button" role="tab" '
                f'aria-selected="{selected}" aria-controls="{panel_id}" id="{panel_id}-tab">'
                f"{_render_inline_markdown(section_title)}</button>"
            )
            panel_content = "\n".join(section["content"])  # type: ignore[arg-type]
            tab_panels.append(
                f'<section class="tab-panel" id="{panel_id}" role="tabpanel" '
                f'aria-labelledby="{panel_id}-tab"{hidden}>'
                f"<h2>{_render_inline_markdown(section_title)}</h2>\n{panel_content}</section>"
            )
        body_html = (
            f"{intro_html}\n"
            f'<div class="tabs" role="tablist" aria-label="周报分类">\n'
            f"{''.join(tab_buttons)}\n</div>\n"
            f"{''.join(tab_panels)}"
        )
    else:
        body_html = intro_html
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html_title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f4;
      --text: #1d1d1f;
      --muted: #6f6f6f;
      --rule: #d9d7d0;
      --link: #0b63ce;
      --surface: #ffffff;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111312;
        --text: #f4f1ea;
        --muted: #a8a29a;
        --rule: #343834;
        --link: #7ab7ff;
        --surface: #171a18;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.72;
    }}
    main {{
      width: min(760px, 100%);
      margin: 0 auto;
      padding: 28px 18px 56px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 2.2rem;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 34px 0 12px;
      font-size: 1.25rem;
      line-height: 1.3;
      letter-spacing: 0;
    }}
    .tabs {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 6px;
      margin: 18px 0 22px;
      padding: 4px;
      border: 1px solid var(--rule);
      border-radius: 8px;
      background: var(--surface);
      background: color-mix(in srgb, var(--surface) 94%, transparent);
      box-shadow: 0 8px 24px rgb(0 0 0 / 8%);
      position: sticky;
      top: max(0px, env(safe-area-inset-top));
      z-index: 20;
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
    }}
    .tab-button {{
      min-height: 42px;
      border: 0;
      border-radius: 6px;
      background: transparent;
      color: var(--muted);
      font: inherit;
      font-weight: 700;
      letter-spacing: 0;
      padding: 8px 6px;
      cursor: pointer;
    }}
    .tab-button.is-active {{
      background: var(--text);
      color: var(--bg);
    }}
    .tab-panel[hidden] {{
      display: none;
    }}
    @media (max-width: 520px) {{
      main {{
        padding: 24px 12px 48px;
      }}
      h1 {{
        font-size: 1.85rem;
      }}
      .tabs {{
        grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
        gap: 4px;
        top: max(0px, env(safe-area-inset-top));
      }}
      .tab-button {{
        min-height: 38px;
        padding: 7px 4px;
        font-size: 0.9rem;
      }}
    }}
    p {{
      margin: 8px 0 14px;
      color: var(--muted);
    }}
    ol {{
      margin: 0;
      padding: 0;
      list-style: none;
      counter-reset: item;
    }}
    li {{
      counter-increment: item;
      margin: 10px 0;
      padding: 14px 15px 14px 48px;
      background: var(--surface);
      border: 1px solid var(--rule);
      border-radius: 8px;
      position: relative;
    }}
    li::before {{
      content: counter(item);
      position: absolute;
      left: 15px;
      top: 16px;
      width: 22px;
      height: 22px;
      border-radius: 999px;
      background: var(--text);
      color: var(--bg);
      font-size: 0.82rem;
      line-height: 22px;
      text-align: center;
      font-weight: 700;
    }}
    a {{
      color: var(--link);
      text-decoration-thickness: 0.08em;
      text-underline-offset: 0.18em;
    }}
    strong {{ font-weight: 700; }}
    code {{
      padding: 0.1em 0.35em;
      border-radius: 5px;
      background: color-mix(in srgb, var(--rule) 55%, transparent);
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.92em;
    }}
    hr {{
      border: 0;
      border-top: 1px solid var(--rule);
      margin: 22px 0;
    }}
  </style>
</head>
<body>
  <main>
{body_html}
  </main>
  <script>
    const tabs = Array.from(document.querySelectorAll('.tab-button'));
    const panels = Array.from(document.querySelectorAll('.tab-panel'));
    tabs.forEach((tab) => {{
      tab.addEventListener('click', () => {{
        tabs.forEach((item) => {{
          item.classList.toggle('is-active', item === tab);
          item.setAttribute('aria-selected', item === tab ? 'true' : 'false');
        }});
        panels.forEach((panel) => {{
          panel.hidden = panel.id !== tab.getAttribute('aria-controls');
        }});
      }});
    }});
  </script>
</body>
</html>
"""
