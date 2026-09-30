"""Remove only unreferenced generated raw files older than 24 hours. No source mutation."""

import re
import time

from sqlalchemy import select

from doculens.config import Settings
from doculens.storage.database import Database
from doculens.storage.models import Version
from doculens.storage.repository import Repository

settings = Settings()
repo = Repository(Database(settings), settings)
with repo.db.transaction() as session:
    referenced = set(session.scalars(select(Version.storage_key)))
removed = 0
for path in repo.files.iterdir():
    if (
        path.is_file()
        and re.fullmatch(r"[0-9a-f-]{36}\.(pdf|markdown|text)", path.name)
        and path.name not in referenced
        and path.stat().st_mtime < time.time() - 86400
    ):
        path.unlink()
        removed += 1
print(f"Removed {removed} unreferenced files after the 24-hour grace period.")
