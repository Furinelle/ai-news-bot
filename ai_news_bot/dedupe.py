from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import NewsItem


TRACKING_PREFIXES = ("utm_",)
TRACKING_KEYS = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid"}
EVENT_STOP_WORDS = {
    "a",
    "after",
    "amid",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "its",
    "new",
    "of",
    "on",
    "over",
    "says",
    "the",
    "to",
    "with",
}
EVENT_TOKEN_ALIASES = {
    "alleged": "allege",
    "allegedly": "allege",
    "lawsuit": "sue",
    "removed": "remove",
    "removes": "remove",
    "shut": "remove",
    "shuts": "remove",
    "stole": "theft",
    "stolen": "theft",
    "stealing": "theft",
    "sued": "sue",
    "sues": "sue",
    "suing": "sue",
    "turned": "remove",
    "turns": "remove",
}
MONTH_NAMES = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().casefold()


@lru_cache(maxsize=4096)
def event_tokens(title: str) -> frozenset[str]:
    text = html.unescape(normalize_title(title))
    text = re.sub(r"\b(?:turn(?:s|ed)?|shut(?:s)?)\s+off\b", " remove ", text)
    raw_tokens = re.findall(r"[a-z0-9]+(?:[.+#-][a-z0-9]+)*", text)
    tokens = {
        EVENT_TOKEN_ALIASES.get(token, token)
        for token in raw_tokens
        if token not in EVENT_STOP_WORDS and len(token) > 1
    }
    return frozenset(tokens)


def same_event(first_title: str, second_title: str) -> bool:
    first = html.unescape(normalize_title(first_title))
    second = html.unescape(normalize_title(second_title))
    if not first or not second:
        return False
    if first == second:
        return True

    first_discriminators = event_discriminators(first)
    second_discriminators = event_discriminators(second)
    if first_discriminators and second_discriminators and first_discriminators != second_discriminators:
        return False

    first_tokens = event_tokens(first_title)
    second_tokens = event_tokens(second_title)
    shared = first_tokens & second_tokens
    if len(shared) < 3:
        return False

    sequence_similarity = SequenceMatcher(None, first, second).ratio()
    if sequence_similarity >= 0.74:
        return True

    shorter_size = min(len(first_tokens), len(second_tokens))
    overlap = len(shared) / shorter_size if shorter_size else 0.0
    return len(shared) >= 4 and overlap >= 0.66


def event_discriminators(normalized_title: str) -> frozenset[str]:
    words = set(re.findall(r"[a-z]+", normalized_title))
    numbers = set(re.findall(r"\b\d+(?:[.-]\d+)*\b", normalized_title))
    return frozenset((words & MONTH_NAMES) | numbers)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    netloc = parts.netloc.lower()
    path = parts.path.rstrip("/")
    if netloc == "github.com":
        path = path.lower()
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in TRACKING_KEYS and not key.startswith(TRACKING_PREFIXES)
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            netloc,
            path,
            urlencode(query),
            "",
        )
    )


def dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[NewsItem] = []

    for item in items:
        url_key = normalize_url(item.url)
        title_key = normalize_title(item.title)
        if (
            url_key in seen_urls
            or title_key in seen_titles
            or any(same_event(item.title, existing.title) for existing in result)
        ):
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        result.append(item)

    return result
