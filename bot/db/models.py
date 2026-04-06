from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GlobalSettings:
    admin_user_id: Optional[str] = None
    mistral_api_key_enc: Optional[str] = None  # Fernet-encrypted, base64
    idle_timeout_seconds: Optional[int] = None
    session_report_enabled: bool = False
    report_guild_id: Optional[str] = None
    report_channel_id: Optional[str] = None


@dataclass
class GuildSettings:
    guild_id: str
    idle_timeout_seconds: Optional[int] = None
    channel_whitelist: list[str] = field(default_factory=list)


@dataclass
class GuildSpeaker:
    guild_id: str
    user_id: str
    voice_id: str
