"""A shared, atomic request budget for the opt-in public sample provider.

One application process serves the free host. State survives process restarts on
the same filesystem; the provider's account quota still applies after disk resets.
"""

import sqlite3
import time
from pathlib import Path

from doculens.errors import DomainError


class PublicAnswerQuota:
    def __init__(self, path: Path, interval: int, daily_limit: int):
        self.path, self.interval, self.daily_limit = path, interval, daily_limit

    def consume(self, now: float | None = None):
        now = time.time() if now is None else now
        day = int(now // 86400)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=5) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS quota (id INTEGER PRIMARY KEY, day INTEGER, count INTEGER, last REAL)"
            )
            record = connection.execute("SELECT day, count, last FROM quota WHERE id=1").fetchone()
            count = record[1] if record and record[0] == day else 0
            if count >= self.daily_limit:
                raise DomainError(
                    "public_answer_quota",
                    "Today's shared free AI answer limit is reached. Search remains available; try again tomorrow (UTC).",
                    429,
                )
            if record and now - record[2] < self.interval:
                seconds = max(1, int(self.interval - (now - record[2])) + 1)
                raise DomainError(
                    "public_answer_quota",
                    f"The shared free AI service is busy. Try again in {seconds} seconds.",
                    429,
                )
            connection.execute(
                "INSERT OR REPLACE INTO quota (id, day, count, last) VALUES (1, ?, ?, ?)",
                (day, count + 1, now),
            )
