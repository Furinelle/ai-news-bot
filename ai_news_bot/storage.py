from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .dedupe import normalize_url, same_event
from .models import INTEREST_CATEGORY, NewsItem


class NewsStore:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_urls (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS telegram_github_sent (
                url TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                title TEXT NOT NULL,
                sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (url, chat_id)
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS news_candidates (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL,
                published_at TEXT,
                score REAL NOT NULL DEFAULT 0,
                tags_json TEXT NOT NULL DEFAULT '[]',
                discovered_on TEXT NOT NULL,
                last_observed_on TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS interest_recommended (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                recommended_on TEXT NOT NULL
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_candidates_discovered_on ON news_candidates(discovered_on)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_interest_recommended_on ON interest_recommended(recommended_on)"
        )
        self._backfill_normalized_seen_urls()
        self._backfill_normalized_telegram_github_urls()
        self.connection.commit()

    def filter_new(
        self,
        items: list[NewsItem],
        *,
        trending_cooldown_days: int = 7,
        interest_cooldown_days: int = 21,
    ) -> list[NewsItem]:
        """按类别冷却过滤。新闻永久去重；Trending/兴趣用冷却窗口。"""
        seen_rows = self.connection.execute(
            "SELECT url, title, seen_at FROM seen_urls"
        ).fetchall()
        seen_map = {url: (title, seen_at) for url, title, seen_at in seen_rows}
        permanent_titles = [title for title, _seen_at in ((t, s) for _u, t, s in seen_rows)]

        interest_cooled = self.interest_urls_in_cooldown(interest_cooldown_days)
        now = datetime.now(ZoneInfo("Asia/Shanghai"))

        result = []
        for item in items:
            key = normalize_url(item.url)

            if item.category == INTEREST_CATEGORY:
                if key in interest_cooled:
                    continue
                result.append(item)
                continue

            if item.category == "GitHub Trending":
                if key in seen_map:
                    _title, seen_at = seen_map[key]
                    if not self._is_older_than(seen_at, trending_cooldown_days, now):
                        continue
                result.append(item)
                continue

            # 普通新闻：永久去重
            if key in seen_map:
                continue
            if any(same_event(item.title, title) for title in permanent_titles):
                continue
            result.append(item)
        return result

    def interest_urls_in_cooldown(self, cooldown_days: int) -> set[str]:
        if cooldown_days <= 0:
            rows = self.connection.execute("SELECT url FROM interest_recommended").fetchall()
            return {str(url) for (url,) in rows}
        cutoff = (
            datetime.now(ZoneInfo("Asia/Shanghai")) - timedelta(days=cooldown_days)
        ).strftime("%Y-%m-%d")
        rows = self.connection.execute(
            "SELECT url FROM interest_recommended WHERE recommended_on >= ?",
            (cutoff,),
        ).fetchall()
        return {str(url) for (url,) in rows}

    def mark_interest_recommended(self, items: list[NewsItem], recommended_on: str) -> None:
        interest_items = [item for item in items if item.category == INTEREST_CATEGORY]
        if not interest_items:
            return
        self.connection.executemany(
            """
            INSERT INTO interest_recommended (url, title, recommended_on)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                recommended_on = excluded.recommended_on
            """,
            [
                (normalize_url(item.url), item.title, recommended_on)
                for item in interest_items
            ],
        )
        self.connection.commit()

    @staticmethod
    def _is_older_than(seen_at: str, days: int, now: datetime) -> bool:
        if days <= 0:
            return False
        try:
            # SQLite CURRENT_TIMESTAMP is UTC-ish 'YYYY-MM-DD HH:MM:SS'
            parsed = datetime.fromisoformat(str(seen_at).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))
        except ValueError:
            try:
                parsed = datetime.strptime(str(seen_at)[:10], "%Y-%m-%d").replace(
                    tzinfo=ZoneInfo("Asia/Shanghai")
                )
            except ValueError:
                return False
        return (now - parsed.astimezone(ZoneInfo("Asia/Shanghai"))) >= timedelta(days=days)

    def remember_candidates(self, items: list[NewsItem], discovered_on: str) -> None:
        self.connection.executemany(
            """
            INSERT INTO news_candidates (
                url, title, source, summary, category, published_at,
                score, tags_json, discovered_on, last_observed_on
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                source = excluded.source,
                summary = excluded.summary,
                category = excluded.category,
                published_at = excluded.published_at,
                score = excluded.score,
                tags_json = excluded.tags_json,
                last_observed_on = excluded.last_observed_on
            """,
            [
                (
                    normalize_url(item.url),
                    item.title,
                    item.source,
                    item.summary,
                    item.category,
                    item.published_at,
                    item.score,
                    json.dumps(item.tags, ensure_ascii=False),
                    discovered_on,
                    discovered_on,
                )
                for item in items
            ],
        )
        self.connection.commit()

    def candidates_discovered_on(self, discovered_on: str) -> list[NewsItem]:
        rows = self.connection.execute(
            """
            SELECT title, url, source, summary, category, published_at, score, tags_json
            FROM news_candidates
            WHERE discovered_on = ?
            ORDER BY rowid
            """,
            (discovered_on,),
        ).fetchall()
        return self._rows_to_items(rows)

    def candidates_discovered_between(self, start_on: str, end_on: str) -> list[NewsItem]:
        """返回 discovered_on 落在 [start_on, end_on]（含两端）的候选。"""
        rows = self.connection.execute(
            """
            SELECT title, url, source, summary, category, published_at, score, tags_json
            FROM news_candidates
            WHERE discovered_on >= ? AND discovered_on <= ?
            ORDER BY discovered_on DESC, rowid
            """,
            (start_on, end_on),
        ).fetchall()
        return self._rows_to_items(rows)

    @staticmethod
    def _rows_to_items(rows: list) -> list[NewsItem]:
        return [
            NewsItem(
                title=title,
                url=url,
                source=source,
                summary=summary,
                category=category,
                published_at=published_at,
                score=float(score),
                tags=json.loads(tags_json),
            )
            for title, url, source, summary, category, published_at, score, tags_json in rows
        ]

    def candidate_discovery_days(self, items: list[NewsItem]) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in items:
            key = normalize_url(item.url)
            row = self.connection.execute(
                "SELECT discovered_on FROM news_candidates WHERE url = ?",
                (key,),
            ).fetchone()
            if row is not None:
                result[key] = str(row[0])
        return result

    def candidate_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM news_candidates").fetchone()[0])

    def mark_seen(self, items: list[NewsItem], recommended_on: str | None = None) -> None:
        """新闻与 Trending 写入 seen；兴趣写入冷却表，不进永久新闻 seen。"""
        news_like = [item for item in items if item.category != INTEREST_CATEGORY]
        interest = [item for item in items if item.category == INTEREST_CATEGORY]
        if news_like:
            self.connection.executemany(
                "INSERT OR IGNORE INTO seen_urls (url, title, source) VALUES (?, ?, ?)",
                [(normalize_url(item.url), item.title, item.source) for item in news_like],
            )
            # Trending 再次推荐时刷新 seen_at
            self.connection.executemany(
                """
                UPDATE seen_urls
                SET title = ?, source = ?, seen_at = CURRENT_TIMESTAMP
                WHERE url = ?
                """,
                [
                    (item.title, item.source, normalize_url(item.url))
                    for item in news_like
                    if item.category == "GitHub Trending"
                ],
            )
        if interest:
            day = recommended_on or datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
            self.mark_interest_recommended(interest, day)
        self.connection.commit()

    def clear_seen(self) -> int:
        cursor = self.connection.execute("DELETE FROM seen_urls")
        self.connection.commit()
        return int(cursor.rowcount or 0)

    def filter_unsent_telegram_github(self, urls: list[str], chat_id: str) -> list[str]:
        result = []
        for url in urls:
            key = normalize_url(url)
            exists = self.connection.execute(
                "SELECT 1 FROM telegram_github_sent WHERE url = ? AND chat_id = ?",
                (key, chat_id),
            ).fetchone()
            if exists is None:
                result.append(url)
        return result

    def mark_telegram_github_sent(self, entries: list[tuple[str, str]], chat_id: str) -> None:
        self.connection.executemany(
            "INSERT OR IGNORE INTO telegram_github_sent (url, chat_id, title) VALUES (?, ?, ?)",
            [(normalize_url(url), chat_id, title) for url, title in entries],
        )
        self.connection.commit()

    def _backfill_normalized_seen_urls(self) -> None:
        rows = self.connection.execute("SELECT url, title, source FROM seen_urls").fetchall()
        self.connection.executemany(
            "INSERT OR IGNORE INTO seen_urls (url, title, source) VALUES (?, ?, ?)",
            [(normalize_url(url), title, source) for url, title, source in rows],
        )

    def _backfill_normalized_telegram_github_urls(self) -> None:
        rows = self.connection.execute("SELECT url, chat_id, title FROM telegram_github_sent").fetchall()
        self.connection.executemany(
            "INSERT OR IGNORE INTO telegram_github_sent (url, chat_id, title) VALUES (?, ?, ?)",
            [(normalize_url(url), chat_id, title) for url, chat_id, title in rows],
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "NewsStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
