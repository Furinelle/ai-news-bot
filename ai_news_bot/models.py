from __future__ import annotations

from dataclasses import dataclass, field

# 周报第四节：个性化 GitHub 兴趣推荐
INTEREST_CATEGORY = "你可能感兴趣"


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    source: str
    summary: str = ""
    category: str = "科技热点"
    published_at: str | None = None
    score: float = 0.0
    tags: list[str] = field(default_factory=list)
