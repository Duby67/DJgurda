"""Unit-tests for atomic stats updates."""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# test/middlewares/db/processing/test_stats_processor.py -> project root это parents[4]
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("BOT_DB_PATH", str(PROJECT_ROOT / "src" / "data" / "db" / "bot.db"))
os.environ.setdefault("BOT_VERSION", "local-test")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("BOT_TOKEN", "local-test-token")
os.environ.setdefault("YANDEX_MUSIC_TOKEN", "local-test-token")

from src.middlewares.db.models.base import Base
from src.middlewares.db.models.sources import Source
from src.middlewares.db.models.stats import Stats

stats_processor_module = importlib.import_module("src.middlewares.db.processing.stats_processor")


async def _prepare_test_database(monkeypatch: Any, db_path: Path) -> tuple[Any, Any]:
    """Создает isolated SQLite database и подменяет session factory в модуле."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}",
        echo=False,
        future=True,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(stats_processor_module, "AsyncSessionLocal", session_factory)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine, session_factory


async def _read_state(session_factory: Any) -> tuple[list[Source], list[Stats]]:
    """Считывает текущие Source/Stats строки из тестовой БД."""
    async with session_factory() as session:
        source_rows = (await session.execute(select(Source))).scalars().all()
        stats_rows = (await session.execute(select(Stats))).scalars().all()
    return source_rows, stats_rows


async def _run_sequential_stats_updates(monkeypatch: Any, tmp_path: Path) -> None:
    engine, session_factory = await _prepare_test_database(monkeypatch, tmp_path / "stats-sequential.db")
    try:
        await stats_processor_module.update_stats(101, 202, "YouTube")
        await stats_processor_module.update_stats(101, 202, "YouTube")

        source_rows, stats_rows = await _read_state(session_factory)

        assert len(source_rows) == 1
        assert source_rows[0].name == "YouTube"
        assert len(stats_rows) == 1
        assert stats_rows[0].chat_id == 101
        assert stats_rows[0].user_id == 202
        assert stats_rows[0].source_id == source_rows[0].id
        assert stats_rows[0].count == 2
    finally:
        await engine.dispose()


async def _run_concurrent_stats_updates(monkeypatch: Any, tmp_path: Path) -> None:
    engine, session_factory = await _prepare_test_database(monkeypatch, tmp_path / "stats-concurrent.db")
    try:
        await asyncio.gather(
            *(stats_processor_module.update_stats(303, 404, "TikTok") for _ in range(4))
        )

        source_rows, stats_rows = await _read_state(session_factory)

        assert len(source_rows) == 1
        assert source_rows[0].name == "TikTok"
        assert len(stats_rows) == 1
        assert stats_rows[0].chat_id == 303
        assert stats_rows[0].user_id == 404
        assert stats_rows[0].source_id == source_rows[0].id
        assert stats_rows[0].count == 4
    finally:
        await engine.dispose()


def test_update_stats_creates_single_source_row_and_increments_count(monkeypatch: Any, tmp_path: Path) -> None:
    asyncio.run(_run_sequential_stats_updates(monkeypatch, tmp_path))


def test_update_stats_concurrent_calls_keep_single_rows_and_accumulate_counts(monkeypatch: Any, tmp_path: Path) -> None:
    asyncio.run(_run_concurrent_stats_updates(monkeypatch, tmp_path))
