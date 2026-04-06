from __future__ import annotations

import re
from typing import Optional

import discord

# Patterns for sanitization
_USER_MENTION = re.compile(r"<@!?(\d+)>")
_ROLE_MENTION = re.compile(r"<@&\d+>")
_CHANNEL_MENTION = re.compile(r"<#\d+>")
_CUSTOM_EMOJI = re.compile(r"<a?:\w+:\d+>")
_URL = re.compile(r"https?://\S+")

MAX_TTS_LENGTH = 4000


def sanitize_message(message: discord.Message) -> Optional[str]:
    text = message.content

    # Resolve user mentions to display names
    def _resolve_user(match: re.Match) -> str:
        uid = int(match.group(1))
        if message.guild:
            member = message.guild.get_member(uid)
            if member:
                return member.display_name
        return "someone"

    text = _USER_MENTION.sub(_resolve_user, text)
    text = _ROLE_MENTION.sub("", text)
    text = _CHANNEL_MENTION.sub("", text)
    text = _CUSTOM_EMOJI.sub("", text)
    text = _URL.sub("", text)

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return None

    return text
