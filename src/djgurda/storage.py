"""SQLite storage for chat settings."""

import sqlite3
from dataclasses import astuple
from pathlib import Path

from djgurda.media import Info

# Bump only for incompatible changes. Additive tables use IF NOT EXISTS, so a rollback to the
# previous release still opens the database.
SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, active INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS captions (chat_id INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS media_cache (
    key TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    cover_id TEXT,
    title TEXT NOT NULL,
    uploader TEXT NOT NULL,
    duration INTEGER,
    width INTEGER,
    height INTEGER
);
CREATE TABLE IF NOT EXISTS deliveries (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL
);
"""


class Storage:
    def __init__(self, path: Path) -> None:
        self._db = sqlite3.connect(path, autocommit=True)
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self._db.close()
            raise RuntimeError(
                f"Database {path} has schema {version}; this version supports {SCHEMA_VERSION}"
            )
        self._db.executescript(f"BEGIN; {SCHEMA} PRAGMA user_version = {SCHEMA_VERSION}; COMMIT;")

    def active_chats(self) -> set[int]:
        return {row[0] for row in self._db.execute("SELECT id FROM chats WHERE active")}

    def set_active(self, chat_id: int, active: bool) -> None:
        self._db.execute(
            "INSERT INTO chats (id, active) VALUES (?, ?)"
            " ON CONFLICT (id) DO UPDATE SET active = excluded.active",
            (chat_id, active),
        )

    def caption(self, chat_id: int) -> bool:
        """Whether deliveries to the chat carry the source and sender caption."""
        query = "SELECT 1 FROM captions WHERE chat_id = ?"
        return self._db.execute(query, (chat_id,)).fetchone() is not None

    def set_caption(self, chat_id: int, enabled: bool) -> None:
        if enabled:
            self._db.execute("INSERT OR IGNORE INTO captions VALUES (?)", (chat_id,))
        else:
            self._db.execute("DELETE FROM captions WHERE chat_id = ?", (chat_id,))

    def cached(self, key: str) -> tuple[str, str | None, Info] | None:
        """Return the video file_id, the cover file_id and the metadata."""
        row = self._db.execute(
            "SELECT file_id, cover_id, title, uploader, duration, width, height"
            " FROM media_cache WHERE key = ?",
            (key,),
        ).fetchone()
        return (row[0], row[1], Info(*row[2:])) if row else None

    def cache(self, key: str, file_id: str, cover_id: str | None, info: Info) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO media_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (key, file_id, cover_id, *astuple(info)),
        )

    def forget(self, key: str, file_id: str) -> None:
        """Drop an unusable file_id; a newer one cached meanwhile stays."""
        self._db.execute("DELETE FROM media_cache WHERE key = ? AND file_id = ?", (key, file_id))

    def begin(self, delivery_id: str, state: str) -> int:
        """Record a delivery until it ends and return how many times it has started."""
        row = self._db.execute(
            "INSERT INTO deliveries VALUES (?, ?, 1) ON CONFLICT (id)"
            " DO UPDATE SET state = excluded.state, attempts = attempts + 1 RETURNING attempts",
            (delivery_id, state),
        ).fetchone()
        return int(row[0])

    def save(self, delivery_id: str, state: str) -> None:
        self._db.execute("UPDATE deliveries SET state = ? WHERE id = ?", (state, delivery_id))

    def end(self, delivery_id: str) -> None:
        self._db.execute("DELETE FROM deliveries WHERE id = ?", (delivery_id,))

    def unfinished(self) -> list[tuple[str, str]]:
        """Deliveries a restart interrupted, oldest first: id and JSON state."""
        return list(self._db.execute("SELECT id, state FROM deliveries ORDER BY rowid"))

    def close(self) -> None:
        self._db.close()
