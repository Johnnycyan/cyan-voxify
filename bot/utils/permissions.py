from __future__ import annotations

import discord

from bot.db import queries


async def is_admin(user_id: int) -> bool:
    gs = await queries.get_global_settings()
    return gs.admin_user_id == str(user_id)


async def is_speaker(guild_id: int, user_id: int) -> bool:
    speaker = await queries.get_speaker(str(guild_id), str(user_id))
    return speaker is not None


def has_manage_guild(member: discord.Member) -> bool:
    return member.guild_permissions.manage_guild
