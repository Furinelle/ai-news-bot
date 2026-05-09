from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import ConfigError, load_config
from .dedupe import dedupe_items
from .fetch_github import fetch_github_trending
from .fetch_hn import fetch_hacker_news
from .fetch_rss import fetch_rss_feed
from .llm import LlmError, summarize_with_llm
from .models import NewsItem
from .pushplus import send_pushplus
from .rank import select_report_items
from .render import default_date_label, render_fallback_report
from .storage import NewsStore


def load_sources(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def collect_items(sources: dict, max_items: int) -> list[NewsItem]:
    items: list[NewsItem] = []

    for rss in sources.get("rss", []):
        rss_items = fetch_rss_feed(
            url=rss["url"],
            source=rss["name"],
            category=rss.get("category", "科技热点"),
        )
        items.extend(rss_items[: int(rss.get("limit", 20))])

    hn = sources.get("hacker_news", {})
    if hn.get("enabled", True):
        items.extend(fetch_hacker_news(limit=int(hn.get("limit", 20))))

    github = sources.get("github_trending", {})
    if github.get("enabled", True):
        for language in github.get("languages", [""]):
            items.extend(
                fetch_github_trending(
                    language=language,
                    since=github.get("since", "daily"),
                    limit=int(github.get("limit", 10)),
                )
            )

    return select_report_items(dedupe_items(items), limit=max_items)


def build_report(
    config_path: str,
    sources_path: str,
    use_llm: bool = True,
    mark_seen: bool = True,
) -> tuple[str, list[NewsItem]]:
    config = load_config(config_path)
    sources = load_sources(sources_path)
    items = collect_items(sources, max_items=config.limits.max_items)
    date_label = default_date_label()

    with NewsStore(config.database_path) as store:
        new_items = store.filter_new(items)
        selected = select_report_items(new_items, limit=config.limits.max_report_items)
        if use_llm and selected:
            report = summarize_with_llm(
                base_url=config.llm.base_url,
                api_key=config.llm.api_key,
                model=config.llm.model,
                items=selected,
                date_label=date_label,
                temperature=config.llm.temperature,
                timeout_seconds=config.llm.timeout_seconds,
            )
        else:
            report = render_fallback_report(selected, date_label=date_label)
        if mark_seen:
            store.mark_seen(selected)
    return report, selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and push a daily technology/AI news report.")
    parser.add_argument("--config", default="config.json", help="Path to config JSON.")
    parser.add_argument("--sources", default="sources.json", help="Path to sources JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Print report without sending it.")
    parser.add_argument("--send", action="store_true", help="Send report through pushplus.")
    parser.add_argument("--no-llm", action="store_true", help="Render a source-link report without calling the LLM.")
    parser.add_argument("--out", default="", help="Optional path to write the generated report.")
    args = parser.parse_args()

    try:
        report, selected = build_report(
            args.config,
            args.sources,
            use_llm=not args.no_llm,
            mark_seen=args.send and not args.dry_run,
        )
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(report, encoding="utf-8")

        if args.dry_run or not args.send:
            print(report)
            print(f"\nSelected items: {len(selected)}")
            return 0

        config = load_config(args.config)
        result = send_pushplus(
            token=config.pushplus.token,
            title="科技与AI日报",
            content=report,
            channel=config.pushplus.channel,
            template=config.pushplus.template,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ConfigError, LlmError, OSError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
