"""Lightweight SQLite schema upgrades for existing athletecore.db files."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

_MEMORY_V2_COLUMNS: tuple[tuple[str, str], ...] = (
    ("event_date", "DATE"),
    ("event_date_end", "DATE"),
    ("raw_user_text", "TEXT"),
    ("source", "VARCHAR(64)"),
    ("sport", "VARCHAR(64)"),
    ("session_type", "VARCHAR(64)"),
    ("facts", "JSON"),
    ("schema_version", "INTEGER DEFAULT 1"),
)


async def ensure_memory_schema_v2(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(memories)"))
        existing = {row[1] for row in result.fetchall()}
        for col_name, col_type in _MEMORY_V2_COLUMNS:
            if col_name in existing:
                continue
            await conn.execute(
                text(f"ALTER TABLE memories ADD COLUMN {col_name} {col_type}")
            )
