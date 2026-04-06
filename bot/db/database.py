from __future__ import annotations

import os
from pathlib import Path

import aiosqlite

from bot.config import DB_PATH

_SCHEMA = """
CREATE TABLE IF NOT EXISTS global_settings (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    admin_user_id          TEXT,
    mistral_api_key_enc    TEXT,
    idle_timeout_seconds   INTEGER,
    session_report_enabled INTEGER NOT NULL DEFAULT 0,
    report_guild_id        TEXT,
    report_channel_id      TEXT
);

INSERT OR IGNORE INTO global_settings (id) VALUES (1);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id             TEXT PRIMARY KEY,
    idle_timeout_seconds INTEGER,
    channel_whitelist    TEXT  -- JSON array of channel-id strings
);

CREATE TABLE IF NOT EXISTS guild_speakers (
    guild_id TEXT NOT NULL,
    user_id  TEXT NOT NULL,
    voice_id TEXT NOT NULL,
    PRIMARY KEY (guild_id, user_id)
);
"""


async def get_connection() -> aiosqlite.Connection:
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        Path(db_dir).mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    return conn


async def init_db() -> None:
    conn = await get_connection()
    try:
        await conn.executescript(_SCHEMA)
        await conn.commit()
    finally:
        await conn.close()
