from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Item


class DigestStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                stable_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def filter_unseen(self, items: list[Item]) -> list[Item]:
        if not items:
            return []
        ids = [item.stable_id for item in items]
        placeholders = ",".join("?" for _ in ids)
        rows = self.conn.execute(
            f"SELECT stable_id FROM items WHERE stable_id IN ({placeholders})",
            ids,
        ).fetchall()
        seen = {row[0] for row in rows}
        return [item for item in items if item.stable_id not in seen]

    def mark_seen(self, items: list[Item]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.conn:
            for item in items:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO items
                    (stable_id, source_id, title, url, published_at, first_seen_at, last_seen_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.stable_id,
                        item.source_id,
                        item.title,
                        item.url,
                        item.published_key,
                        now,
                        now,
                    ),
                )
                self.conn.execute(
                    "UPDATE items SET last_seen_at = ? WHERE stable_id = ?",
                    (now, item.stable_id),
                )

    def filter_new(self, items: list[Item]) -> list[Item]:
        fresh = self.filter_unseen(items)
        self.mark_seen(fresh)
        return fresh
