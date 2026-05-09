from __future__ import annotations

import sqlite3
from pathlib import Path

from .dedupe import normalize_url
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
        self.connection.commit()

    def filter_new(self, items: list[NewsItem]) -> list[NewsItem]:
        result = []
        for item in items:
            key = normalize_url(item.url)
            exists = self.connection.execute(
                "SELECT 1 FROM seen_urls WHERE url = ?",
                (key,),
            ).fetchone()
            if exists is None:
                result.append(item)
        return result

    def mark_seen(self, items: list[NewsItem]) -> None:
        self.connection.executemany(
            "INSERT OR IGNORE INTO seen_urls (url, title, source) VALUES (?, ?, ?)",
            [(normalize_url(item.url), item.title, item.source) for item in items],
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "NewsStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

