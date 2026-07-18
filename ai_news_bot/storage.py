from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .dedupe import normalize_url, same_event
from .models import NewsItem


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
            "CREATE INDEX IF NOT EXISTS idx_news_candidates_discovered_on ON news_candidates(discovered_on)"
        )
        self._backfill_normalized_seen_urls()
        self._backfill_normalized_telegram_github_urls()
        self.connection.commit()

    def filter_new(self, items: list[NewsItem]) -> list[NewsItem]:
        seen_rows = self.connection.execute("SELECT url, title FROM seen_urls").fetchall()
        seen_urls = {url for url, _title in seen_rows}
        seen_titles = [title for _url, title in seen_rows]
        result = []
        for item in items:
            key = normalize_url(item.url)
            if key in seen_urls:
                continue
            if any(same_event(item.title, title) for title in seen_titles):
                continue
            result.append(item)
        return result

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

    def mark_seen(self, items: list[NewsItem]) -> None:
        self.connection.executemany(
            "INSERT OR IGNORE INTO seen_urls (url, title, source) VALUES (?, ?, ?)",
            [(normalize_url(item.url), item.title, item.source) for item in items],
        )
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
