from __future__ import annotations

import logging

import discord

from bot.config import DISCORD_TOKEN
from bot.db.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("voxify")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = discord.Bot(intents=intents)


@bot.event
async def on_ready() -> None:
    await init_db()
    log.info("Database initialised")
    log.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)  # type: ignore[union-attr]


bot.load_extension("bot.cogs.settings")
bot.load_extension("bot.cogs.tts")

bot.run(DISCORD_TOKEN)
