from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import option
from discord.ext import commands

from bot.db import queries
from bot.services.session import TTSSession, get_session_manager
from bot.services.tts import TTSService
from bot.utils.permissions import is_admin, is_speaker
from bot.utils.sanitize import MAX_TTS_LENGTH, sanitize_message

log = logging.getLogger(__name__)


class TTS(commands.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot
        self._sm = get_session_manager()

    # ── /tts ───────────────────────────────────────────────────────────────

    @commands.slash_command(
        name="tts", description="Start TTS in your current voice channel"
    )
    @option(
        "user",
        discord.User,
        description="User to listen for (admin only – speakers target themselves)",
        required=False,
    )
    async def tts_cmd(
        self,
        ctx: discord.ApplicationContext,
        user: Optional[discord.User] = None,
    ) -> None:
        if ctx.guild is None:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        await ctx.defer(ephemeral=True)

        guild_id = ctx.guild.id
        caller_id = ctx.author.id
        caller_is_admin = await is_admin(caller_id)
        caller_is_speaker = await is_speaker(guild_id, caller_id)

        # --- permission gate -------------------------------------------------
        if not caller_is_admin and not caller_is_speaker:
            await ctx.followup.send(
                "Only the bot admin or a configured speaker can use this command.",
            )
            return

        # --- determine target speaker ----------------------------------------
        if caller_is_admin and user is not None:
            target_user = user
        elif caller_is_speaker:
            target_user = ctx.author
        elif caller_is_admin and user is None:
            await ctx.followup.send(
                "As admin, specify which user to listen for: `/tts user:@someone`.",
            )
            return
        else:
            await ctx.followup.send("Unable to determine target speaker.")
            return

        target_id = str(target_user.id)

        # --- validate settings -----------------------------------------------
        missing: list[str] = []
        api_key = await queries.get_api_key()
        if api_key is None:
            missing.append("Mistral API key (`/config global apikey`)")

        speaker = await queries.get_speaker(str(guild_id), target_id)
        if speaker is None:
            missing.append(
                f"Voice ID for {target_user.mention} (`/config guild add-speaker`)"
            )

        if missing:
            await ctx.followup.send(
                "Missing configuration:\n• " + "\n• ".join(missing),
            )
            return

        voice_id = speaker.voice_id  # type: ignore[union-attr]

        # --- caller must be in a voice channel --------------------------------
        member = ctx.guild.get_member(caller_id)
        if member is None or member.voice is None or member.voice.channel is None:
            await ctx.followup.send("You need to join a voice channel first.")
            return

        target_vc = member.voice.channel

        # --- handle existing session -----------------------------------------
        session = self._sm.get(guild_id)
        if session is not None:
            if session.voice_client.channel.id != target_vc.id:
                await ctx.followup.send(
                    f"The bot is already in {session.voice_client.channel.mention}. "
                    "Join that channel first, then run `/tts` again.",
                )
                return

            # Already in the same VC — add speaker
            session.add_speaker(target_id, voice_id, str(ctx.channel_id))
            await ctx.followup.send(
                f"Now also listening to {target_user.mention} in this channel. 🔊",
            )
            return

        # --- join voice channel -----------------------------------------------
        try:
            vc: discord.VoiceClient = await target_vc.connect()  # type: ignore[assignment]
        except discord.Forbidden:
            await ctx.followup.send(
                f"I don't have permission to join {target_vc.mention}.",
            )
            return
        except discord.ClientException:
            await ctx.followup.send(
                "I'm already connected to a voice channel in this server.",
            )
            return

        # --- create session ---------------------------------------------------
        tts_service = TTSService(api_key)  # type: ignore[arg-type]
        session = TTSSession(
            guild=ctx.guild,
            voice_client=vc,
            tts_service=tts_service,
            bot=self.bot,
        )
        self._sm.set(guild_id, session)
        await session.start(target_id, voice_id, str(ctx.channel_id))

        await ctx.followup.send(
            f"TTS started! Listening to {target_user.mention} in this channel. 🔊",
        )

    # ── /stop ──────────────────────────────────────────────────────────────

    @commands.slash_command(name="stop", description="Stop TTS in this server")
    async def stop_cmd(self, ctx: discord.ApplicationContext) -> None:
        if ctx.guild is None:
            await ctx.respond(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        guild_id = ctx.guild.id
        session = self._sm.get(guild_id)
        if session is None:
            await ctx.respond("No active TTS session in this server.", ephemeral=True)
            return

        caller_id = ctx.author.id
        caller_is_admin = await is_admin(caller_id)
        caller_str = str(caller_id)
        caller_is_active_speaker = caller_str in session.speakers

        if not caller_is_admin and not caller_is_active_speaker:
            await ctx.respond(
                "Only the bot admin or an active speaker can stop the session.",
                ephemeral=True,
            )
            return

        if caller_is_admin:
            # Admin kills the whole session
            await session.stop()
            self._sm.remove(guild_id)
            await ctx.respond("TTS session stopped. 🔇", ephemeral=True)
        else:
            # Speaker removes only themselves
            empty = session.remove_speaker(caller_str)
            if empty:
                await session.stop()
                self._sm.remove(guild_id)
                await ctx.respond(
                    "You were the last speaker — TTS session stopped. 🔇",
                    ephemeral=True,
                )
            else:
                await ctx.respond(
                    "You've been removed from the active session.", ephemeral=True
                )

    # ── on_message listener ────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.guild is None:
            return

        session = self._sm.get(message.guild.id)
        if session is None:
            return

        author_id = str(message.author.id)
        speaker_info = session.speakers.get(author_id)
        if speaker_info is None:
            return

        # Must be from the channel where /tts was invoked for this speaker
        if str(message.channel.id) != speaker_info.channel_id:
            return

        # Channel whitelist check
        whitelist = await queries.get_channel_whitelist(str(message.guild.id))
        if whitelist and str(message.channel.id) not in whitelist:
            return

        # Sanitize
        cleaned = sanitize_message(message)
        if cleaned is None:
            return

        # Ignore command-like messages
        if cleaned.startswith("!"):
            return

        # Truncation warning
        if len(cleaned) > MAX_TTS_LENGTH:
            try:
                await message.add_reaction("\u26a0\ufe0f")
            except discord.HTTPException:
                pass

        await session.enqueue(message, cleaned)

    # ── auto-disconnect on empty VC ────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.id == self.bot.user.id:  # type: ignore[union-attr]
            # The bot itself was disconnected externally
            if before.channel is not None and after.channel is None:
                session = self._sm.get(member.guild.id)
                if session is not None:
                    await session.stop()
                    self._sm.remove(member.guild.id)
            return

        # A human left a VC — check if the bot is now alone
        if before.channel is None:
            return

        session = self._sm.get(member.guild.id)
        if session is None:
            return

        if session.voice_client.channel.id != before.channel.id:
            return

        # Count non-bot members remaining
        humans = [m for m in before.channel.members if not m.bot]
        if len(humans) == 0:
            log.info(
                "All users left VC in guild %s – stopping session", member.guild.id
            )
            await session.stop()
            self._sm.remove(member.guild.id)


def setup(bot: discord.Bot) -> None:
    bot.add_cog(TTS(bot))
