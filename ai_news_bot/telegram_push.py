from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Callable

from .dedupe import normalize_url


DEFAULT_TELEGRAM_API_BASE = "https://api.telegram.org"


class TelegramPushError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramSendResult:
    ok: bool
    sent: int
    failed: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class TelegramGitHubMessage:
    title: str
    url: str
    text: str


def extract_github_trending_entries(report: str) -> list[TelegramGitHubMessage]:
    """提取 GitHub Trending 与「你可能感兴趣」两节中的仓库条目。"""
    entries: list[TelegramGitHubMessage] = []
    seen_urls: set[str] = set()
    in_github_section = False

    for raw_line in report.splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            heading = line.casefold()
            in_github_section = (
                ("github trending" in heading)
                or ("你可能感兴趣" in line)
                or ("可能感兴趣" in line)
            )
            continue
        if not in_github_section:
            continue
        if not line:
            continue
        match = re.match(r"^\d+\.\s+(.*)$", line)
        if not match:
            continue
        entry = build_telegram_github_entry(match.group(1))
        if entry and normalize_url(entry.url) not in seen_urls:
            entries.append(entry)
            seen_urls.add(normalize_url(entry.url))

    return entries


def extract_github_trending_messages(report: str) -> list[str]:
    return [entry.text for entry in extract_github_trending_entries(report)]


def build_telegram_github_entry(markdown_item: str) -> TelegramGitHubMessage | None:
    match = re.match(r"^\[([^\]]+)\]\((https?://[^)]+)\)\s*(.*)$", markdown_item.strip())
    if not match:
        return None

    title, url, description = match.groups()
    if "github.com/" not in url:
        return None

    link = f'<a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>'
    description = description.strip()
    text = link if not description else f"{link} {html.escape(description)}"
    return TelegramGitHubMessage(title=title, url=url, text=text)


def build_telegram_github_message(markdown_item: str) -> str:
    entry = build_telegram_github_entry(markdown_item)
    return entry.text if entry else ""


def build_telegram_payload(
    chat_id: str,
    text: str,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = False,
) -> dict[str, object]:
    return {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }


def send_telegram_messages(
    bot_token: str,
    chat_id: str,
    messages: list[str],
    endpoint_base: str = DEFAULT_TELEGRAM_API_BASE,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = False,
    post: Callable[..., Any] | None = None,
) -> TelegramSendResult:
    if not messages:
        return TelegramSendResult(ok=True, sent=0)
    if not bot_token:
        raise TelegramPushError("telegram bot token is required")
    if not chat_id:
        raise TelegramPushError("telegram chat_id is required")

    endpoint = f"{endpoint_base.rstrip('/')}/bot{bot_token}/sendMessage"
    sent = 0

    if post is None:
        import httpx

        with httpx.Client(timeout=30) as client:
            for message in messages:
                _send_one(
                    post=client.post,
                    endpoint=endpoint,
                    chat_id=chat_id,
                    text=message,
                    parse_mode=parse_mode,
                    disable_web_page_preview=disable_web_page_preview,
                )
                sent += 1
    else:
        for message in messages:
            _send_one(
                post=post,
                endpoint=endpoint,
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
            )
            sent += 1

    return TelegramSendResult(ok=True, sent=sent)


def _send_one(
    post: Callable[..., Any],
    endpoint: str,
    chat_id: str,
    text: str,
    parse_mode: str,
    disable_web_page_preview: bool,
) -> None:
    payload = build_telegram_payload(
        chat_id=chat_id,
        text=text,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
    )
    response = post(endpoint, json=payload, timeout=30)
    try:
        body = response.json()
    except ValueError:
        body = {"ok": True}
    try:
        response.raise_for_status()
    except Exception as exc:
        description = body.get("description", "Telegram API HTTP error")
        status_code = getattr(response, "status_code", "unknown")
        raise TelegramPushError(f"Telegram API HTTP {status_code}: {description}") from exc
    if not body.get("ok", False):
        description = body.get("description", "unknown Telegram API error")
        raise TelegramPushError(str(description))
