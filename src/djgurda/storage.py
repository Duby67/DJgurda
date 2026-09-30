"""SQLite storage for chat settings."""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1


class Storage:
    def __init__(self, path: Path) -> None:
        self._db = sqlite3.connect(path, autocommit=True)
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            self._db.executescript(
                f"""
                BEGIN;
                CREATE TABLE chats (id INTEGER PRIMARY KEY, active INTEGER NOT NULL);
                PRAGMA user_version = {SCHEMA_VERSION};
                COMMIT;
                """
            )
        elif version != SCHEMA_VERSION:
            self._db.close()
            raise RuntimeError(
                f"Database {path} has schema {version}; this version supports {SCHEMA_VERSION}"
            )

    def active_chats(self) -> set[int]:
        return {row[0] for row in self._db.execute("SELECT id FROM chats WHERE active")}

    def set_active(self, chat_id: int, active: bool) -> None:
        self._db.execute(
            "INSERT INTO chats (id, active) VALUES (?, ?)"
            " ON CONFLICT (id) DO UPDATE SET active = excluded.active",
            (chat_id, active),
        )

    def close(self) -> None:
        self._db.close()
