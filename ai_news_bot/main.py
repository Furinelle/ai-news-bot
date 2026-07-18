from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .blog import BlogPublishError, BlogPublishResult, publish_report_to_blog
from .config import ConfigError, load_config
from .dedupe import dedupe_items, normalize_url
from .fetch_github import fetch_github_trending
from .fetch_hn import fetch_hacker_news
from .fetch_json_api import fetch_json_api
from .fetch_rss import fetch_rss_feed
from .llm import LlmError, summarize_with_llm
from .models import NewsItem
from .pushplus import send_pushplus
from .r2 import R2UploadResult, build_r2_key, create_presigned_get_url, upload_file_to_r2
from .rank import select_report_items, select_report_items_with_fallback
from .remote_push import send_remote_push
from .render import default_date_label, render_fallback_report, render_html_report
from .storage import NewsStore
from .telegram_push import (
    TelegramSendResult,
    extract_github_trending_entries,
    send_telegram_messages,
)


def load_sources(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def warn(message: str) -> None:
    print(f"WARN: {message}", file=sys.stderr)


def collect_items(sources: dict, max_items: int) -> list[NewsItem]:
    items: list[NewsItem] = []

    for rss in sources.get("rss", []):
        try:
            rss_items = fetch_rss_feed(
                url=rss["url"],
                source=rss["name"],
                category=rss.get("category", "科技热点"),
            )
        except Exception as exc:
            warn(f"skipping RSS source {rss.get('name', rss.get('url', '<unknown>'))}: {exc}")
            continue
        items.extend(rss_items[: int(rss.get("limit", 20))])

    for api in sources.get("json_apis", []):
        try:
            api_items = fetch_json_api(
                url=api["url"],
                source=api["name"],
                category=api.get("category", "科技热点"),
                items_path=api.get("items_path", "results"),
                title_fields=api.get("title_fields"),
                url_fields=api.get("url_fields"),
                summary_fields=api.get("summary_fields"),
                published_fields=api.get("published_fields"),
                source_fields=api.get("source_fields"),
            )
        except Exception as exc:
            warn(f"skipping JSON API source {api.get('name', api.get('url', '<unknown>'))}: {exc}")
            continue
        items.extend(api_items[: int(api.get("limit", 20))])

    hn = sources.get("hacker_news", {})
    if hn.get("enabled", True):
        try:
            items.extend(fetch_hacker_news(limit=int(hn.get("limit", 20))))
        except Exception as exc:
            warn(f"skipping Hacker News: {exc}")

    items.extend(collect_github_trending_items(sources.get("github_trending", {})))

    return select_report_items(dedupe_items(items), limit=max_items)


def collect_github_trending_items(github: dict) -> list[NewsItem]:
    if not github.get("enabled", True):
        return []

    items: list[NewsItem] = []
    github_limit = int(github.get("limit", 10))
    since_values = _github_since_values(github)
    for language in github.get("languages", [""]):
        language_items: list[NewsItem] = []
        for since in since_values:
            if len(dedupe_items(language_items)) >= github_limit:
                break
            try:
                language_items.extend(
                    fetch_github_trending(
                        language=language,
                        since=since,
                        limit=github_limit,
                    )
                )
                language_items = dedupe_items(language_items)
            except Exception as exc:
                label = language or "all"
                warn(f"skipping GitHub Trending source {label}/{since}: {exc}")
        items.extend(language_items[:github_limit])
    return items


def _github_since_values(github: dict) -> list[str]:
    raw_since = github.get("since", "daily")
    if isinstance(raw_since, list):
        values = [str(value) for value in raw_since]
    else:
        values = [str(raw_since)]
    values.extend(str(value) for value in github.get("extra_since", []))
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result or ["daily"]


def build_report(
    config_path: str,
    sources_path: str,
    use_llm: bool = True,
    mark_seen: bool = True,
    persist_candidates: bool | None = None,
    report_date: date | None = None,
) -> tuple[str, list[NewsItem]]:
    config = load_config(config_path)
    sources = load_sources(sources_path)
    items = collect_items(sources, max_items=config.limits.max_items)
    date_label = default_date_label()
    report_date = report_date or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    yesterday = report_date - timedelta(days=1)
    if persist_candidates is None:
        persist_candidates = mark_seen

    with NewsStore(config.database_path) as store:
        bootstrap_candidates = store.candidate_count() == 0
        if persist_candidates:
            remember_collected_candidates(
                store,
                items,
                report_date=report_date,
                infer_published_date=bootstrap_candidates,
            )
            primary_candidates = store.candidates_discovered_on(report_date.isoformat())
        else:
            discovery_days = store.candidate_discovery_days(items)
            primary_candidates = [
                item
                for item in items
                if discovery_days.get(normalize_url(item.url), report_date.isoformat()) == report_date.isoformat()
            ]
            primary_candidates.extend(store.candidates_discovered_on(report_date.isoformat()))

        new_items = dedupe_items(store.filter_new(primary_candidates))
        yesterday_items = dedupe_items(
            store.filter_new(store.candidates_discovered_on(yesterday.isoformat()))
        )
        combined = dedupe_items([*new_items, *yesterday_items])
        yesterday_items = combined[len(new_items) :]
        selected = select_report_items_with_fallback(
            primary_items=new_items,
            fallback_items=yesterday_items,
            limit=config.limits.max_report_items,
        )
        if use_llm and selected:
            report = summarize_with_llm(
                base_url=config.llm.base_url,
                api_key=config.llm.api_key,
                model=config.llm.model,
                items=selected,
                date_label=date_label,
                temperature=config.llm.temperature,
                timeout_seconds=config.llm.timeout_seconds,
                thinking_enabled=config.llm.thinking_enabled,
                reasoning_effort=config.llm.reasoning_effort,
            )
        else:
            report = render_fallback_report(selected, date_label=date_label)
        if mark_seen:
            store.mark_seen(selected)
    return report, selected


def remember_collected_candidates(
    store: NewsStore,
    items: list[NewsItem],
    report_date: date,
    infer_published_date: bool = False,
) -> None:
    grouped: dict[str, list[NewsItem]] = {}
    for item in items:
        discovered_on = report_date
        if infer_published_date:
            published_date = parse_published_date(item.published_at)
            if published_date is not None and published_date <= report_date:
                discovered_on = published_date
        grouped.setdefault(discovered_on.isoformat(), []).append(item)
    for discovered_on, candidates in grouped.items():
        store.remember_candidates(candidates, discovered_on=discovered_on)


def parse_published_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed.astimezone(ZoneInfo("Asia/Shanghai")).date()


def default_report_slug() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")


def write_report_files(report: str, output_dir: str, slug: str, latest_name: str) -> tuple[Path, Path]:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{slug}.md"
    latest_path = report_dir / latest_name
    report_path.write_text(report, encoding="utf-8")
    latest_path.write_text(report, encoding="utf-8")
    return report_path, latest_path


def write_html_report_files(report: str, output_dir: str, slug: str) -> tuple[Path, Path]:
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    html = render_html_report(report)
    report_path = report_dir / f"{slug}.html"
    latest_path = report_dir / "latest.html"
    report_path.write_text(html, encoding="utf-8")
    latest_path.write_text(html, encoding="utf-8")
    return report_path, latest_path


def mark_items_seen(config_path: str, items: list[NewsItem]) -> None:
    config = load_config(config_path)
    with NewsStore(config.database_path) as store:
        store.mark_seen(items)


def upload_report_files(
    config_path: str,
    report_path: Path,
    latest_path: Path,
    slug: str,
    html_report_path: Path | None = None,
    html_latest_path: Path | None = None,
) -> list[R2UploadResult]:
    config = load_config(config_path)
    if not config.r2.enabled:
        return []
    if not config.r2.bucket:
        raise ConfigError("r2.bucket is required when R2 upload is enabled")
    if not config.r2.endpoint_url:
        raise ConfigError("r2.endpoint_url or Cloudflare account ID is required when R2 upload is enabled")
    if not config.r2.access_key_id:
        raise ConfigError("R2 access key ID is required when R2 upload is enabled")
    if not config.r2.secret_access_key:
        raise ConfigError("R2 secret access key is required when R2 upload is enabled")

    daily_key = build_r2_key(config.r2.key_prefix, f"{slug}.md")
    latest_key = build_r2_key(config.r2.key_prefix, latest_path.name)
    uploads = [
        upload_file_to_r2(
            path=report_path,
            bucket=config.r2.bucket,
            key=daily_key,
            endpoint_url=config.r2.endpoint_url,
            access_key_id=config.r2.access_key_id,
            secret_access_key=config.r2.secret_access_key,
            public_base_url=config.r2.public_base_url,
            content_type=config.r2.content_type,
        ),
        upload_file_to_r2(
            path=latest_path,
            bucket=config.r2.bucket,
            key=latest_key,
            endpoint_url=config.r2.endpoint_url,
            access_key_id=config.r2.access_key_id,
            secret_access_key=config.r2.secret_access_key,
            public_base_url=config.r2.public_base_url,
            content_type=config.r2.content_type,
        ),
    ]
    if html_report_path and html_latest_path:
        html_daily_key = build_r2_key(config.r2.key_prefix, f"{slug}.html")
        html_latest_key = build_r2_key(config.r2.key_prefix, "latest.html")
        uploads.extend(
            [
                upload_file_to_r2(
                    path=html_report_path,
                    bucket=config.r2.bucket,
                    key=html_daily_key,
                    endpoint_url=config.r2.endpoint_url,
                    access_key_id=config.r2.access_key_id,
                    secret_access_key=config.r2.secret_access_key,
                    public_base_url=config.r2.public_base_url,
                    content_type="text/html; charset=utf-8",
                ),
                upload_file_to_r2(
                    path=html_latest_path,
                    bucket=config.r2.bucket,
                    key=html_latest_key,
                    endpoint_url=config.r2.endpoint_url,
                    access_key_id=config.r2.access_key_id,
                    secret_access_key=config.r2.secret_access_key,
                    public_base_url=config.r2.public_base_url,
                    content_type="text/html; charset=utf-8",
                ),
            ]
        )
        if not config.r2.public_base_url:
            html_url = create_presigned_get_url(
                bucket=config.r2.bucket,
                key=html_daily_key,
                endpoint_url=config.r2.endpoint_url,
                access_key_id=config.r2.access_key_id,
                secret_access_key=config.r2.secret_access_key,
                expires_seconds=config.r2.presigned_url_expires_seconds,
            )
            uploads[-2] = R2UploadResult(bucket=config.r2.bucket, key=html_daily_key, url=html_url)
    return uploads


def build_push_body(date_label: str, selected_count: int, report_url: str) -> str:
    lines = [
        f"{date_label} 科技/AI日报已发布到博客。",
        f"入选新闻：{selected_count} 条。",
    ]
    if report_url:
        lines.append(report_url)
    return "\n".join(lines)


def summarize_remote_push_result(result: dict[str, object]) -> dict[str, object]:
    data = result.get("data")
    if not isinstance(data, dict):
        return result
    return {
        "ok": result.get("ok"),
        "message": result.get("message"),
        "push_id": data.get("push_id"),
        "target_devices": data.get("target_devices"),
        "daily_limit": data.get("daily_limit"),
        "remaining": data.get("remaining"),
        "timestamp": result.get("timestamp"),
    }


def summarize_upload_results(uploads: list[R2UploadResult]) -> list[dict[str, object]]:
    return [
        {
            "bucket": upload.bucket,
            "key": upload.key,
            "has_url": bool(upload.url),
        }
        for upload in uploads
    ]


def summarize_telegram_result(result: object) -> dict[str, object] | None:
    if result is None:
        return None
    return {
        "ok": getattr(result, "ok", False),
        "sent": getattr(result, "sent", 0),
        "failed": getattr(result, "failed", 0),
        "skipped": getattr(result, "skipped", 0),
    }


def summarize_blog_result(result: BlogPublishResult | None) -> dict[str, object] | None:
    if result is None:
        return None
    return {
        "feed_id": result.feed_id,
        "alias": result.alias,
        "url": result.url,
        "created": result.created,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and push a daily technology/AI news report.")
    parser.add_argument("--config", default="config.json", help="Path to config JSON.")
    parser.add_argument("--sources", default="sources.json", help="Path to sources JSON.")
    parser.add_argument("--dry-run", action="store_true", help="Print report without sending it.")
    parser.add_argument("--send", action="store_true", help="Upload report and send it through Scripting Remote Push.")
    parser.add_argument("--send-pushplus", action="store_true", help="Also send report through pushplus when configured.")
    parser.add_argument("--no-llm", action="store_true", help="Render a source-link report without calling the LLM.")
    parser.add_argument("--no-r2", action="store_true", help="Skip R2 upload even when r2.enabled is true.")
    parser.add_argument("--out", default="", help="Optional path to write the generated report.")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
        slug = default_report_slug()
        report, selected = build_report(
            args.config,
            args.sources,
            use_llm=not args.no_llm,
            mark_seen=False,
            persist_candidates=args.send,
        )

        if args.dry_run or not args.send:
            if args.out:
                out_path = Path(args.out)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(report, encoding="utf-8")
            print(report)
            print(f"\nSelected items: {len(selected)}")
            return 0

        if args.out:
            report_path = Path(args.out)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report, encoding="utf-8")
            latest_path = report_path
            html_report_path = None
            html_latest_path = None
        else:
            report_path, latest_path = write_report_files(
                report=report,
                output_dir=config.report.output_dir,
                slug=slug,
                latest_name=config.report.latest_name,
            )
            html_report_path, html_latest_path = write_html_report_files(
                report=report,
                output_dir=config.report.output_dir,
                slug=slug,
            )

        uploads = [] if args.no_r2 else upload_report_files(
            args.config,
            report_path,
            latest_path,
            slug,
            html_report_path=html_report_path,
            html_latest_path=html_latest_path,
        )
        report_url = next((upload.url for upload in uploads if upload.key.endswith(f"{slug}.html") and upload.url), "")
        if not report_url:
            report_url = next((upload.url for upload in uploads if upload.key.endswith(f"{slug}.md") and upload.url), "")
        blog_result = None
        if config.blog.enabled:
            if not config.blog.base_url:
                raise ConfigError("blog.base_url is required when blog publishing is enabled")
            if not config.blog.username:
                raise ConfigError("BLOG_ADMIN_USERNAME is required when blog publishing is enabled")
            if not config.blog.password:
                raise ConfigError("BLOG_ADMIN_PASSWORD is required when blog publishing is enabled")
            blog_result = publish_report_to_blog(
                base_url=config.blog.base_url,
                username=config.blog.username,
                password=config.blog.password,
                report=report,
                slug=slug,
                selected_count=len(selected),
                title_prefix=config.blog.title_prefix,
                tags=config.blog.tags,
            )
            report_url = blog_result.url
        if not config.scripting_push.enabled:
            raise ConfigError("scripting_push.enabled must be true when --send is used")
        if not config.scripting_push.api_key:
            raise ConfigError("SCRIPTING_PUSH_API_KEY is required when --send is used")
        push_result = send_remote_push(
            api_key=config.scripting_push.api_key,
            endpoint=config.scripting_push.endpoint,
            title=config.scripting_push.title,
            body=build_push_body(default_date_label(), len(selected), report_url),
            action=report_url,
        )
        pushplus_result = None
        if args.send_pushplus:
            if not config.pushplus.token:
                raise ConfigError("pushplus token is required when --send-pushplus is used")
            pushplus_result = send_pushplus(
                token=config.pushplus.token,
                title="科技与AI日报",
                content=report,
                channel=config.pushplus.channel,
                template=config.pushplus.template,
            )

        telegram_result = None
        if config.telegram.enabled:
            if not config.telegram.bot_token:
                raise ConfigError("TELEGRAM_BOT_TOKEN is required when telegram.enabled is true")
            if not config.telegram.chat_id:
                raise ConfigError("telegram.chat_id is required when telegram.enabled is true")
            try:
                telegram_entries = extract_github_trending_entries(report)
                with NewsStore(config.database_path) as store:
                    unsent_urls = set(
                        normalize_url(url)
                        for url in store.filter_unsent_telegram_github(
                            [entry.url for entry in telegram_entries],
                            config.telegram.chat_id,
                        )
                    )
                unsent_entries = [entry for entry in telegram_entries if normalize_url(entry.url) in unsent_urls]
                telegram_result = send_telegram_messages(
                    bot_token=config.telegram.bot_token,
                    chat_id=config.telegram.chat_id,
                    messages=[entry.text for entry in unsent_entries],
                    endpoint_base=config.telegram.endpoint_base,
                    disable_web_page_preview=config.telegram.disable_web_page_preview,
                )
                with NewsStore(config.database_path) as store:
                    store.mark_telegram_github_sent(
                        [(entry.url, entry.title) for entry in unsent_entries],
                        config.telegram.chat_id,
                    )
                telegram_result = TelegramSendResult(
                    ok=telegram_result.ok,
                    sent=telegram_result.sent,
                    failed=telegram_result.failed,
                    skipped=len(telegram_entries) - len(unsent_entries),
                )
            except Exception as exc:
                warn(f"Telegram push failed: {exc}")

        mark_items_seen(args.config, selected)
        result = {
            "report_path": str(report_path),
            "selected_items": len(selected),
            "r2_uploads": summarize_upload_results(uploads),
            "blog": summarize_blog_result(blog_result),
            "remote_push": summarize_remote_push_result(push_result),
            "pushplus": pushplus_result,
            "telegram": summarize_telegram_result(telegram_result),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BlogPublishError, ConfigError, LlmError, OSError, KeyError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
