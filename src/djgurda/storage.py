"""SQLite storage for chat settings."""

import sqlite3
from pathlib import Path

# Bump only for incompatible changes. Additive tables use IF NOT EXISTS, so a rollback to the
# previous release still opens the database.
SCHEMA_VERSION = 1
SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, active INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS nicknames (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    PRIMARY KEY (chat_id, user_id)
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

    def nickname(self, chat_id: int, user_id: int) -> str | None:
        row = self._db.execute(
            "SELECT name FROM nicknames WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        ).fetchone()
        return row[0] if row else None

    def set_nickname(self, chat_id: int, user_id: int, name: str | None) -> None:
        if name is None:
            self._db.execute(
                "DELETE FROM nicknames WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
            )
            return
        self._db.execute(
            "INSERT INTO nicknames (chat_id, user_id, name) VALUES (?, ?, ?)"
            " ON CONFLICT (chat_id, user_id) DO UPDATE SET name = excluded.name",
            (chat_id, user_id, name),
        )

    def close(self) -> None:
        self._db.close()
