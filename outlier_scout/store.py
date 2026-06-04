from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import List


class Store:
    """Remembers which video IDs have already been emailed."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS reported ("
            "  video_id TEXT PRIMARY KEY,"
            "  first_reported TEXT NOT NULL"
            ")"
        )
        self._conn.commit()

    def is_reported(self, video_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM reported WHERE video_id = ?", (video_id,)
        )
        return cur.fetchone() is not None

    def mark_reported(self, video_ids: List[str], when: datetime) -> None:
        self._conn.executemany(
            "INSERT OR IGNORE INTO reported (video_id, first_reported) "
            "VALUES (?, ?)",
            [(vid, when.isoformat()) for vid in video_ids],
        )
        self._conn.commit()
