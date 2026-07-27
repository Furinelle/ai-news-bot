from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "your",
    "you",
    "are",
    "not",
    "can",
    "into",
    "based",
    "using",
    "open",
    "source",
    "tool",
    "tools",
    "project",
    "simple",
    "easy",
    "free",
    "modern",
    "built",
    "support",
    "supports",
    "provide",
    "provides",
    "library",
    "framework",
    "application",
    "app",
    "system",
    "code",
    "github",
    "repo",
    "repository",
    "一个",
    "用于",
    "支持",
    "基于",
    "实现",
    "提供",
    "简单",
    "工具",
    "项目",
    "开源",
}

# 兴趣补充词：在 star 描述稀疏时仍能搜到对口仓库
SEED_KEYWORDS = (
    "claude-code",
    "codex",
    "mcp",
    "agent memory",
    "telegram bot",
    "self-hosted",
    "cloudflare workers",
    "vps",
    "tcp",
    "pixiv",
    "tts",
    "voice clone",
    "rust cli",
    "server monitoring",
)

SEED_TOPICS = (
    "claude-code",
    "ai-agents",
    "mcp",
    "telegram-bot",
    "self-hosted",
    "cloudflare-workers",
    "rust",
    "cli",
    "monitoring",
    "tts",
)


@dataclass
class StarProfile:
    username: str
    starred: list[str] = field(default_factory=list)
    languages: list[tuple[str, int]] = field(default_factory=list)
    topics: list[tuple[str, int]] = field(default_factory=list)
    keywords: list[tuple[str, int]] = field(default_factory=list)
    built_at: float = 0.0

    @property
    def starred_set(self) -> set[str]:
        return {name.casefold() for name in self.starred}

    @property
    def top_languages(self) -> list[str]:
        return [name for name, _ in self.languages]

    @property
    def top_topics(self) -> list[str]:
        return [name for name, _ in self.topics]

    @property
    def top_keywords(self) -> list[str]:
        return [name for name, _ in self.keywords]


def _token_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-news-bot-github-interest/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def resolve_github_token(token: str | None = None, token_env: str = "GITHUB_TOKEN") -> str:
    if token and token.strip():
        return token.strip()
    env_value = os.environ.get(token_env, "").strip()
    if env_value:
        return env_value
    # 兼容 gh 常用环境变量
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def fetch_starred_repos(
    username: str,
    token: str | None = None,
    client: Any | None = None,
    per_page: int = 100,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """通过 GitHub API 拉取用户 star 列表；无 token 时回退到 `gh api`。"""
    import httpx

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=30.0)
    try:
        headers = _token_headers(token)
        repos: list[dict[str, Any]] = []
        url = f"https://api.github.com/users/{username}/starred"
        params = {"per_page": per_page}
        for _ in range(max_pages):
            response = client.get(url, headers=headers, params=params)
            if response.status_code == 401 and not token:
                break
            response.raise_for_status()
            page = response.json()
            if not isinstance(page, list) or not page:
                break
            repos.extend(page)
            next_url = _parse_next_link(response.headers.get("Link", ""))
            if not next_url:
                break
            url = next_url
            params = None  # type: ignore[assignment]
        if repos:
            return repos
    finally:
        if owns_client:
            client.close()

    return _fetch_starred_via_gh(username)


def _parse_next_link(link_header: str) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' not in section:
            continue
        start = section.find("<")
        end = section.find(">")
        if start != -1 and end != -1:
            return section[start + 1 : end]
    return None


def _fetch_starred_via_gh(username: str) -> list[dict[str, Any]]:
    """本机已登录 gh 时的回退路径。"""
    try:
        completed = subprocess.run(
            [
                "gh",
                "api",
                "--paginate",
                f"users/{username}/starred?per_page=100",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"failed to fetch starred repos for {username}: no usable GitHub token and gh api failed ({exc})"
        ) from exc

    return _decode_paginated_json_arrays(completed.stdout)


def _decode_paginated_json_arrays(payload: str) -> list[dict[str, Any]]:
    text = payload.strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    except json.JSONDecodeError:
        pass

    items: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    index = 0
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        chunk, end = decoder.raw_decode(text, index)
        if isinstance(chunk, list):
            items.extend(item for item in chunk if isinstance(item, dict))
        index = end
    return items


def _extract_keywords(text: str) -> list[str]:
    if not text:
        return []
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    return [word for word in words if word not in STOPWORDS and not word.isdigit()]


def build_profile_from_repos(username: str, repos: list[dict[str, Any]]) -> StarProfile:
    language_counter: Counter[str] = Counter()
    topic_counter: Counter[str] = Counter()
    keyword_counter: Counter[str] = Counter()
    starred: list[str] = []

    for repo in repos:
        full_name = str(repo.get("full_name") or "").strip()
        if full_name:
            starred.append(full_name)
        language = repo.get("language")
        if isinstance(language, str) and language.strip():
            language_counter[language.strip()] += 1
        for topic in repo.get("topics") or []:
            if isinstance(topic, str) and topic.strip():
                topic_counter[topic.strip().casefold()] += 1
        description = str(repo.get("description") or "")
        for word in _extract_keywords(description):
            keyword_counter[word] += 1

    for topic in SEED_TOPICS:
        topic_counter[topic] += 1
    for keyword in SEED_KEYWORDS:
        for word in _extract_keywords(keyword):
            keyword_counter[word] += 1

    return StarProfile(
        username=username,
        starred=starred,
        languages=language_counter.most_common(12),
        topics=topic_counter.most_common(24),
        keywords=keyword_counter.most_common(40),
        built_at=time.time(),
    )


def build_star_profile(
    username: str,
    token: str | None = None,
    client: Any | None = None,
    fetch_repos: Callable[..., list[dict[str, Any]]] | None = None,
) -> StarProfile:
    fetcher = fetch_repos or fetch_starred_repos
    repos = fetcher(username=username, token=token, client=client)
    return build_profile_from_repos(username, repos)


def profile_to_dict(profile: StarProfile) -> dict[str, Any]:
    return asdict(profile)


def profile_from_dict(data: dict[str, Any]) -> StarProfile:
    return StarProfile(
        username=str(data.get("username", "")),
        starred=list(data.get("starred") or []),
        languages=[(str(name), int(count)) for name, count in data.get("languages") or []],
        topics=[(str(name), int(count)) for name, count in data.get("topics") or []],
        keywords=[(str(name), int(count)) for name, count in data.get("keywords") or []],
        built_at=float(data.get("built_at") or 0.0),
    )


def load_cached_profile(path: str | Path, ttl_hours: float = 24.0) -> StarProfile | None:
    cache_path = Path(path)
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    profile = profile_from_dict(data)
    if ttl_hours > 0 and profile.built_at > 0:
        age_hours = (time.time() - profile.built_at) / 3600.0
        if age_hours > ttl_hours:
            return None
    return profile


def save_profile(profile: StarProfile, path: str | Path) -> None:
    cache_path = Path(path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(profile_to_dict(profile), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_or_build_profile(
    username: str,
    cache_path: str | Path,
    token: str | None = None,
    ttl_hours: float = 24.0,
    client: Any | None = None,
    force_refresh: bool = False,
) -> StarProfile:
    if not force_refresh:
        cached = load_cached_profile(cache_path, ttl_hours=ttl_hours)
        if cached is not None and cached.username.casefold() == username.casefold():
            return cached
    profile = build_star_profile(username=username, token=token, client=client)
    save_profile(profile, cache_path)
    return profile


def iso_days_ago(days: int) -> str:
    if days <= 0:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return datetime.fromtimestamp(time.time() - days * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
