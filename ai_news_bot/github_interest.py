from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Callable, Iterable

from .models import INTEREST_CATEGORY, NewsItem
from .star_profile import (
    StarProfile,
    _token_headers,
    get_or_build_profile,
    iso_days_ago,
    resolve_github_token,
)

# 描述里出现这些信号，更像「有一技之长」的专用工具，而不是空壳/合集
DISTINCTIVE_BONUS = (
    ("single binary", 4.0),
    ("zero dependency", 3.5),
    ("self-hosted", 3.0),
    ("self hosted", 3.0),
    ("cloudflare workers", 3.5),
    ("cloudflare worker", 3.5),
    ("telegram bot", 3.0),
    ("telegram", 1.5),
    ("mcp server", 3.5),
    ("mcp", 2.0),
    ("claude code", 3.5),
    ("claude-code", 3.5),
    ("codex", 2.5),
    ("agent memory", 4.0),
    ("long-term memory", 3.5),
    ("vector", 1.5),
    ("rss", 1.5),
    ("pixiv", 3.5),
    ("tts", 2.5),
    ("voice clone", 3.5),
    ("voice cloning", 3.5),
    ("wireguard", 3.0),
    ("bbr", 3.0),
    ("tcp", 2.0),
    ("sysctl", 2.5),
    ("monitoring", 2.0),
    ("uptime", 2.0),
    ("proxy", 1.5),
    ("tui", 2.0),
    ("cli", 1.5),
    ("fingerprint", 2.5),
    ("anti-detect", 3.0),
    ("headless", 1.5),
    ("rust", 1.5),
    ("审批", 3.0),
    ("记忆", 2.5),
    ("自托管", 3.0),
    ("单二进制", 3.5),
    ("零样本", 2.5),
    ("变声", 2.5),
    ("爬虫", 2.0),
    ("反代", 2.0),
)

GENERIC_PENALTY = (
    (r"\bawesome[-\s]", 8.0),
    (r"\bcurated list\b", 8.0),
    (r"\bcollection of\b", 5.0),
    (r"\blinks?\b", 1.5),
    (r"\binterview\b", 4.0),
    (r"\bcheatsheet\b", 4.0),
    (r"\blearning resources?\b", 5.0),
    (r"\b教程合集", 6.0),
    (r"\b资源列表", 6.0),
    (r"\b资源大全", 8.0),
    (r"\b大全\b", 6.0),
    (r"\b零基础教程", 7.0),
    (r"\bskills?\s*合集", 6.0),
    (r"\b导航", 3.0),
    (r"\bbilerplate\b", 3.0),
    (r"\btemplate\b", 2.0),
)

# 搜索查询强制覆盖的兴趣簇（避免全被 claude-code 占满）
INTEREST_CLUSTER_QUERIES = (
    "telegram bot (approval OR daemon OR framework) language:Rust",
    "self-hosted (monitoring OR uptime OR dashboard)",
    "cloudflare workers (email OR shortener OR proxy OR status)",
    "mcp server (memory OR context OR code)",
    "agent memory OR long-term memory llm",
    "pixiv (downloader OR client OR bot)",
    "(tts OR \"voice clone\" OR \"voice cloning\")",
    "(bbr OR sysctl OR bufferbloat OR tcp) (vps OR linux OR network)",
    "telegram media downloader OR gallery-dl alternative",
    "single binary cli (tui OR monitor OR proxy) language:Rust",
)


def build_search_queries(
    profile: StarProfile,
    *,
    min_stars: int = 80,
    max_stars: int = 20000,
    pushed_within_days: int = 150,
    created_within_days: int = 365,
    max_queries: int = 12,
) -> list[str]:
    """构造 GitHub 搜索查询：兴趣画像 + 强制兴趣簇，偏中腰部活跃非 fork。"""
    pushed = iso_days_ago(pushed_within_days)
    created = iso_days_ago(created_within_days)
    star_range = f"stars:{min_stars}..{max_stars}"
    common = f"{star_range} pushed:>{pushed} fork:false archived:false"

    queries: list[str] = []

    # 1) 先塞兴趣簇：保证 Telegram / 自托管 / MCP / 网络 等都能搜到
    for cluster in INTEREST_CLUSTER_QUERIES:
        queries.append(f"{cluster} {common}")

    # 2) 画像 topics：跳过过于泛化的词，并限制同族 topic 数量
    generic_topics = {"ai", "llm", "python", "openai", "anthropic", "claude", "agent", "agents"}
    topic_added = 0
    for topic in profile.top_topics:
        safe = re.sub(r"[^\w\-.]", "", topic)
        if not safe or safe in generic_topics:
            continue
        queries.append(f"topic:{safe} {common}")
        topic_added += 1
        if topic_added >= 5:
            break

    # 3) 主力语言 + 能力词
    for language in profile.top_languages[:3]:
        if language.casefold() in {"html", "css", "jupyter notebook"}:
            continue
        queries.append(
            f"language:{language} {common} (cli OR bot OR monitor OR proxy OR memory OR tui OR daemon)"
        )

    # 4) 新晋仓库：创建一年内
    for topic in profile.top_topics:
        safe = re.sub(r"[^\w\-.]", "", topic)
        if not safe or safe in generic_topics:
            continue
        queries.append(
            f"topic:{safe} stars:>={min_stars} created:>{created} pushed:>{pushed} fork:false archived:false"
        )
        break

    unique: list[str] = []
    for query in queries:
        if query not in unique:
            unique.append(query)
    return unique[:max_queries]


def search_repositories(
    query: str,
    token: str | None = None,
    *,
    per_page: int = 15,
    sort: str = "stars",
    order: str = "desc",
    client: Any | None = None,
) -> list[dict[str, Any]]:
    import httpx

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=30.0)
    try:
        response = client.get(
            "https://api.github.com/search/repositories",
            headers=_token_headers(token),
            params={
                "q": query,
                "sort": sort,
                "order": order,
                "per_page": per_page,
            },
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]
    finally:
        if owns_client:
            client.close()


def _repo_text(repo: dict[str, Any]) -> str:
    topics = " ".join(str(t) for t in (repo.get("topics") or []))
    return " ".join(
        [
            str(repo.get("full_name") or ""),
            str(repo.get("description") or ""),
            topics,
            str(repo.get("language") or ""),
        ]
    ).casefold()


def score_repository(repo: dict[str, Any], profile: StarProfile) -> float:
    """兴趣匹配 + 特色功能信号；过滤空描述/合集。"""
    full_name = str(repo.get("full_name") or "").strip()
    if not full_name:
        return -1.0
    if full_name.casefold() in profile.starred_set:
        return -1.0
    if repo.get("fork") or repo.get("archived"):
        return -1.0

    description = str(repo.get("description") or "").strip()
    if len(description) < 12:
        return -1.0

    text = _repo_text(repo)
    score = 0.0

    # 兴趣：topics / language / keywords
    repo_topics = {str(t).casefold() for t in (repo.get("topics") or []) if t}
    for topic, weight in profile.topics[:16]:
        if topic.casefold() in repo_topics or topic.casefold() in text:
            score += 2.5 + min(weight, 8) * 0.15

    language = str(repo.get("language") or "")
    for lang, weight in profile.languages[:8]:
        if language and language.casefold() == lang.casefold():
            score += 2.0 + min(weight, 20) * 0.05
            break

    for keyword, weight in profile.keywords[:20]:
        token = keyword.casefold()
        if len(token) >= 3 and token in text:
            score += 1.2 + min(weight, 10) * 0.08

    # 特色功能加分
    for phrase, bonus in DISTINCTIVE_BONUS:
        if phrase in text:
            score += bonus

    # 通用合集/列表降权
    for pattern, penalty in GENERIC_PENALTY:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score -= penalty

    stars = int(repo.get("stargazers_count") or 0)
    # 偏好中腰部「有验证但未必刷屏」的仓库；巨型仓降权（多半已在 trending/你视野里）
    if 150 <= stars <= 5000:
        score += 3.0
    elif 5000 < stars <= 12000:
        score += 1.0
    elif 12000 < stars <= 25000:
        score -= 2.0
    elif stars > 25000:
        score -= 6.0
    elif stars < 80:
        score -= 1.5

    # 描述越具体越好（有动词/能力词）
    if re.search(r"\b(for|that|which|to|with|without)\b", description, re.I) or any(
        ch in description for ch in "，。、：；"
    ):
        score += 0.8

    # 一句话能说清「专用能力」的加分
    if re.search(
        r"\b(single[- ]binary|zero[- ]dependenc|self[- ]hosted|mcp server|telegram bot|voice clone|wireguard|bufferbloat|sysctl)\b",
        text,
        re.I,
    ) or any(token in description for token in ("单二进制", "自托管", "审批", "记忆", "变声", "反代")):
        score += 2.5

    # 必须有最低兴趣相关度
    if score < 4.0:
        return -1.0
    return score


def repo_to_news_item(repo: dict[str, Any], score: float) -> NewsItem:
    full_name = str(repo.get("full_name") or "").strip()
    description = str(repo.get("description") or "").strip()
    language = str(repo.get("language") or "").strip()
    stars = int(repo.get("stargazers_count") or 0)
    topics = [str(t) for t in (repo.get("topics") or []) if t][:8]
    topic_hint = f" · topics: {', '.join(topics)}" if topics else ""
    lang_hint = f" · {language}" if language else ""
    summary = f"{description}{lang_hint} · ★{stars}{topic_hint}"
    # tags 里塞匹配线索，方便 LLM 写「为什么适合你」
    tags = topics + ([language] if language else []) + [f"stars:{stars}", f"score:{score:.1f}"]
    return NewsItem(
        title=full_name,
        url=str(repo.get("html_url") or f"https://github.com/{full_name}"),
        source="GitHub 兴趣推荐",
        summary=summary,
        category=INTEREST_CATEGORY,
        score=score,
        tags=tags,
        published_at=str(repo.get("pushed_at") or repo.get("updated_at") or "") or None,
    )


def collect_interest_repos(
    profile: StarProfile,
    token: str | None = None,
    *,
    limit: int = 8,
    min_stars: int = 80,
    max_stars: int = 40000,
    pushed_within_days: int = 150,
    max_queries: int = 10,
    per_query: int = 12,
    exclude_urls: Iterable[str] | None = None,
    client: Any | None = None,
    search: Callable[..., list[dict[str, Any]]] | None = None,
) -> list[NewsItem]:
    search_fn = search or search_repositories
    exclude = {url.rstrip("/").casefold() for url in (exclude_urls or [])}
    queries = build_search_queries(
        profile,
        min_stars=min_stars,
        max_stars=max_stars,
        pushed_within_days=pushed_within_days,
        max_queries=max_queries,
    )

    owns_client = client is None and search is None
    if client is None and search is None:
        import httpx

        client = httpx.Client(timeout=30.0)

    best: dict[str, NewsItem] = {}
    try:
        for query in queries:
            try:
                repos = search_fn(query, token=token, per_page=per_query, client=client)
            except Exception:
                continue
            for repo in repos:
                full_name = str(repo.get("full_name") or "").strip()
                if not full_name:
                    continue
                url = str(repo.get("html_url") or f"https://github.com/{full_name}").rstrip("/")
                if url.casefold() in exclude:
                    continue
                score = score_repository(repo, profile)
                if score < 0:
                    continue
                item = repo_to_news_item(repo, score)
                previous = best.get(full_name.casefold())
                if previous is None or item.score > previous.score:
                    best[full_name.casefold()] = item
    finally:
        if owns_client and client is not None:
            client.close()

    ranked = sorted(best.values(), key=lambda item: item.score, reverse=True)
    return diversify_interest_items(ranked, limit=limit)


def _primary_topic_key(item: NewsItem) -> str:
    for tag in item.tags:
        token = str(tag).casefold()
        if token.startswith("stars:") or token.startswith("score:"):
            continue
        # 语言标签单独处理
        if token in {"python", "typescript", "javascript", "rust", "go", "shell", "swift"}:
            continue
        return token
    return "misc"


def diversify_interest_items(items: list[NewsItem], limit: int, max_per_topic: int = 1) -> list[NewsItem]:
    """避免同一 topic（如 claude-code）占满整节，保留特色多样性。"""
    if limit <= 0:
        return []
    selected: list[NewsItem] = []
    topic_counts: dict[str, int] = {}
    owner_counts: dict[str, int] = {}
    deferred: list[NewsItem] = []

    # claude-code 生态相关 topic 共用一个配额桶，防止整节都是 coding agent 插件
    def bucket(key: str) -> str:
        family = {
            "claude-code",
            "claude-code-plugins",
            "claude-code-skills",
            "claude-skills",
            "claude-code-hooks",
            "agent-skills",
            "ai-agents",
            "agentic-ai",
            "coding-agent",
            "codex",
        }
        return "coding-agent-ecosystem" if key in family else key

    for item in items:
        key = bucket(_primary_topic_key(item))
        owner = item.title.split("/", 1)[0].casefold() if "/" in item.title else item.title.casefold()
        if topic_counts.get(key, 0) >= max_per_topic or owner_counts.get(owner, 0) >= 1:
            deferred.append(item)
            continue
        selected.append(item)
        topic_counts[key] = topic_counts.get(key, 0) + 1
        owner_counts[owner] = owner_counts.get(owner, 0) + 1
        if len(selected) >= limit:
            return selected

    for item in deferred:
        if len(selected) >= limit:
            break
        selected.append(item)
    return selected


def fetch_github_interest_items(
    config: dict[str, Any],
    *,
    exclude_urls: Iterable[str] | None = None,
    client: Any | None = None,
) -> list[NewsItem]:
    """sources.json 的 github_interest 入口。"""
    if not config.get("enabled", True):
        return []

    username = str(config.get("username") or config.get("user") or "").strip()
    if not username:
        raise ValueError("github_interest.username is required")

    token = resolve_github_token(
        token=str(config.get("token") or "").strip() or None,
        token_env=str(config.get("token_env") or "GITHUB_TOKEN"),
    )
    cache_path = str(config.get("profile_cache_path") or "data/star_profile.json")
    ttl_hours = float(config.get("profile_ttl_hours", 24))
    force_refresh = bool(config.get("force_refresh_profile", False))

    profile = get_or_build_profile(
        username=username,
        cache_path=cache_path,
        token=token or None,
        ttl_hours=ttl_hours,
        client=client,
        force_refresh=force_refresh,
    )

    return collect_interest_repos(
        profile,
        token=token or None,
        limit=int(config.get("limit", 8)),
        min_stars=int(config.get("min_stars", 80)),
        max_stars=int(config.get("max_stars", 40000)),
        pushed_within_days=int(config.get("pushed_within_days", 150)),
        max_queries=int(config.get("max_queries", 12)),
        per_query=int(config.get("per_query", 12)),
        exclude_urls=exclude_urls,
        client=client,
    )


def annotate_match_reason(item: NewsItem, profile: StarProfile) -> NewsItem:
    """给 summary 追加简短匹配原因，方便无 LLM 时阅读。"""
    reasons: list[str] = []
    text = f"{item.title} {item.summary}".casefold()
    for topic, _ in profile.topics[:12]:
        if topic.casefold() in text:
            reasons.append(f"topic:{topic}")
        if len(reasons) >= 3:
            break
    for lang, _ in profile.languages[:5]:
        if lang.casefold() in text:
            reasons.append(f"lang:{lang}")
            break
    if not reasons:
        return item
    reason_text = "；匹配：" + "、".join(reasons[:4])
    if reason_text in item.summary:
        return item
    return replace(item, summary=f"{item.summary}{reason_text}")
