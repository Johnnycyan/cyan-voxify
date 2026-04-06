from __future__ import annotations

import json
from typing import Optional

from cryptography.fernet import Fernet

from bot.config import DB_ENCRYPTION_KEY
from bot.db.database import get_connection
from bot.db.models import GlobalSettings, GuildSettings, GuildSpeaker, VoiceAfFilter

_fernet = Fernet(DB_ENCRYPTION_KEY.encode())


# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------


async def get_global_settings() -> GlobalSettings:
    conn = await get_connection()
    try:
        cursor = await conn.execute("SELECT * FROM global_settings WHERE id = 1")
        row = await cursor.fetchone()
        if row is None:
            return GlobalSettings()
        return GlobalSettings(
            admin_user_id=row["admin_user_id"],
            mistral_api_key_enc=row["mistral_api_key_enc"],
            idle_timeout_seconds=row["idle_timeout_seconds"],
            session_report_enabled=bool(row["session_report_enabled"]),
            report_guild_id=row["report_guild_id"],
            report_channel_id=row["report_channel_id"],
        )
    finally:
        await conn.close()


async def set_admin(user_id: str) -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE global_settings SET admin_user_id = ? WHERE id = 1",
            (user_id,),
        )
        await conn.commit()
    finally:
        await conn.close()


async def set_api_key(plain_key: str) -> None:
    encrypted = _fernet.encrypt(plain_key.encode()).decode()
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE global_settings SET mistral_api_key_enc = ? WHERE id = 1",
            (encrypted,),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_api_key() -> Optional[str]:
    gs = await get_global_settings()
    if gs.mistral_api_key_enc is None:
        return None
    return _fernet.decrypt(gs.mistral_api_key_enc.encode()).decode()


async def set_global_idle_timeout(seconds: Optional[int]) -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE global_settings SET idle_timeout_seconds = ? WHERE id = 1",
            (seconds,),
        )
        await conn.commit()
    finally:
        await conn.close()


async def set_session_report(
    enabled: bool,
    guild_id: Optional[str] = None,
    channel_id: Optional[str] = None,
) -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            "UPDATE global_settings SET session_report_enabled = ?, "
            "report_guild_id = ?, report_channel_id = ? WHERE id = 1",
            (int(enabled), guild_id, channel_id),
        )
        await conn.commit()
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Guild settings
# ---------------------------------------------------------------------------


async def get_guild_settings(guild_id: str) -> GuildSettings:
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return GuildSettings(guild_id=guild_id)
        whitelist_raw = row["channel_whitelist"]
        whitelist = json.loads(whitelist_raw) if whitelist_raw else []
        return GuildSettings(
            guild_id=row["guild_id"],
            idle_timeout_seconds=row["idle_timeout_seconds"],
            channel_whitelist=whitelist,
        )
    finally:
        await conn.close()


async def set_guild_idle_timeout(guild_id: str, seconds: Optional[int]) -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO guild_settings (guild_id, idle_timeout_seconds) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET idle_timeout_seconds = excluded.idle_timeout_seconds",
            (guild_id, seconds),
        )
        await conn.commit()
    finally:
        await conn.close()


async def set_channel_whitelist(guild_id: str, channel_ids: list[str]) -> None:
    raw = json.dumps(channel_ids) if channel_ids else None
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO guild_settings (guild_id, channel_whitelist) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_whitelist = excluded.channel_whitelist",
            (guild_id, raw),
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_channel_whitelist(guild_id: str) -> list[str]:
    gs = await get_guild_settings(guild_id)
    return gs.channel_whitelist


# ---------------------------------------------------------------------------
# Guild speakers
# ---------------------------------------------------------------------------


async def add_speaker(guild_id: str, user_id: str, voice_id: str) -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO guild_speakers (guild_id, user_id, voice_id) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO UPDATE SET voice_id = excluded.voice_id",
            (guild_id, user_id, voice_id),
        )
        await conn.commit()
    finally:
        await conn.close()


async def remove_speaker(guild_id: str, user_id: str) -> bool:
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "DELETE FROM guild_speakers WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def get_speaker(guild_id: str, user_id: str) -> Optional[GuildSpeaker]:
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM guild_speakers WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return GuildSpeaker(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            voice_id=row["voice_id"],
        )
    finally:
        await conn.close()


async def get_speakers(guild_id: str) -> list[GuildSpeaker]:
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM guild_speakers WHERE guild_id = ?", (guild_id,)
        )
        rows = await cursor.fetchall()
        return [
            GuildSpeaker(
                guild_id=row["guild_id"],
                user_id=row["user_id"],
                voice_id=row["voice_id"],
            )
            for row in rows
        ]
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Voice AF filters
# ---------------------------------------------------------------------------


async def set_voice_af_filter(guild_id: str, voice_id: str, af_filter: str) -> None:
    conn = await get_connection()
    try:
        await conn.execute(
            "INSERT INTO voice_af_filters (guild_id, voice_id, af_filter) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, voice_id) DO UPDATE SET af_filter = excluded.af_filter",
            (guild_id, voice_id, af_filter),
        )
        await conn.commit()
    finally:
        await conn.close()


async def remove_voice_af_filter(guild_id: str, voice_id: str) -> bool:
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "DELETE FROM voice_af_filters WHERE guild_id = ? AND voice_id = ?",
            (guild_id, voice_id),
        )
        await conn.commit()
        return cursor.rowcount > 0
    finally:
        await conn.close()


async def get_voice_af_filter(guild_id: str, voice_id: str) -> Optional[str]:
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT af_filter FROM voice_af_filters WHERE guild_id = ? AND voice_id = ?",
            (guild_id, voice_id),
        )
        row = await cursor.fetchone()
        return row["af_filter"] if row else None
    finally:
        await conn.close()


async def get_all_voice_af_filters(guild_id: str) -> list[VoiceAfFilter]:
    conn = await get_connection()
    try:
        cursor = await conn.execute(
            "SELECT * FROM voice_af_filters WHERE guild_id = ?", (guild_id,)
        )
        rows = await cursor.fetchall()
        return [
            VoiceAfFilter(
                guild_id=row["guild_id"],
                voice_id=row["voice_id"],
                af_filter=row["af_filter"],
            )
            for row in rows
        ]
    finally:
        await conn.close()
