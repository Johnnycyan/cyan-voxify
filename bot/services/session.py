from __future__ import annotations

import asyncio
import io
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import discord

from bot.db import queries
from bot.services.tts import TTSService

log = logging.getLogger(__name__)


@dataclass
class SpeakerInfo:
    user_id: str
    voice_id: str
    channel_id: str  # text channel the speaker activated from


@dataclass
class SessionStats:
    start_time: float = field(default_factory=time.monotonic)
    messages_processed: int = 0
    audio_bytes_generated: int = 0

    @property
    def duration_seconds(self) -> float:
        return time.monotonic() - self.start_time

    @property
    def audio_minutes(self) -> float:
        # WAV 24 kHz mono 16-bit → 48 000 bytes/sec; rough estimate
        if self.audio_bytes_generated <= 44:  # header only
            return 0.0
        data_bytes = self.audio_bytes_generated - 44  # strip WAV header estimate
        return (data_bytes / 48_000) / 60


class TTSSession:
    """Manages one active TTS session in a guild."""

    def __init__(
        self,
        guild: discord.Guild,
        voice_client: discord.VoiceClient,
        tts_service: TTSService,
        bot: discord.Bot,
    ) -> None:
        self.guild = guild
        self.voice_client = voice_client
        self.tts_service = tts_service
        self.bot = bot

        self.speakers: dict[str, SpeakerInfo] = {}
        self._queue: asyncio.Queue[discord.Message] = asyncio.Queue()
        self._process_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._idle_event = asyncio.Event()
        self.stats = SessionStats()
        self._stopped = False

    # -- lifecycle -----------------------------------------------------------

    async def start(
        self,
        user_id: str,
        voice_id: str,
        channel_id: str,
    ) -> None:
        self.add_speaker(user_id, voice_id, channel_id)
        self._process_task = asyncio.create_task(self._process_queue())
        await self._restart_idle_timer()

    def add_speaker(self, user_id: str, voice_id: str, channel_id: str) -> None:
        self.speakers[user_id] = SpeakerInfo(
            user_id=user_id, voice_id=voice_id, channel_id=channel_id
        )

    def remove_speaker(self, user_id: str) -> bool:
        """Remove a speaker.  Returns True if the session is now empty."""
        self.speakers.pop(user_id, None)
        return len(self.speakers) == 0

    async def enqueue(self, message: discord.Message, text: str) -> None:
        await self._queue.put((message, text))
        # Reset idle timer on activity
        self._idle_event.set()

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True

        if self._process_task and not self._process_task.done():
            self._process_task.cancel()
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()

        if self.voice_client.is_connected():
            self.voice_client.stop()
            await self.voice_client.disconnect(force=True)

        await self._send_report()

    # -- queue processor -----------------------------------------------------

    async def _process_queue(self) -> None:
        try:
            while True:
                message, text = await self._queue.get()
                speaker = self.speakers.get(str(message.author.id))
                if speaker is None:
                    continue

                audio = await self.tts_service.generate_speech(text, speaker.voice_id)
                if audio is None:
                    log.warning("TTS generation failed for message %s", message.id)
                    continue

                self.stats.messages_processed += 1
                self.stats.audio_bytes_generated += len(audio)

                if len(message.content) > 4000:
                    try:
                        await message.add_reaction("\u26a0\ufe0f")
                    except discord.HTTPException:
                        pass

                await self._play_audio(audio)
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Queue processor crashed")

    async def _play_audio(self, audio_bytes: bytes) -> None:
        if not self.voice_client.is_connected():
            return

        source = discord.FFmpegPCMAudio(io.BytesIO(audio_bytes), pipe=True)

        done = asyncio.Event()

        def _after(error: Optional[Exception]) -> None:
            if error:
                log.error("Playback error: %s", error)
            self.bot.loop.call_soon_threadsafe(done.set)

        self.voice_client.play(source, after=_after)
        await done.wait()

    # -- idle timer ----------------------------------------------------------

    async def _restart_idle_timer(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = asyncio.create_task(self._idle_loop())

    async def _idle_loop(self) -> None:
        try:
            timeout = await self._effective_timeout()
            if timeout is None:
                return  # no timeout configured

            while True:
                self._idle_event.clear()
                try:
                    await asyncio.wait_for(self._idle_event.wait(), timeout=timeout)
                except asyncio.TimeoutError:
                    log.info(
                        "Idle timeout reached for guild %s – disconnecting",
                        self.guild.id,
                    )
                    await self.stop()
                    # Let the session manager know
                    _session_manager.remove(self.guild.id)
                    return
        except asyncio.CancelledError:
            pass

    async def _effective_timeout(self) -> Optional[float]:
        gs = await queries.get_global_settings()
        guild_s = await queries.get_guild_settings(str(self.guild.id))

        global_t = gs.idle_timeout_seconds
        guild_t = guild_s.idle_timeout_seconds

        if global_t is None and guild_t is None:
            return None
        if global_t is None:
            return float(guild_t)  # type: ignore[arg-type]
        if guild_t is None:
            return float(global_t)
        return float(min(guild_t, global_t))

    # -- session report ------------------------------------------------------

    async def _send_report(self) -> None:
        try:
            gs = await queries.get_global_settings()
            if not gs.session_report_enabled:
                return
            if not gs.report_guild_id or not gs.report_channel_id:
                return

            report_guild = self.bot.get_guild(int(gs.report_guild_id))
            if report_guild is None:
                return
            channel = report_guild.get_channel(int(gs.report_channel_id))
            if channel is None or not isinstance(
                channel, (discord.TextChannel, discord.Thread)
            ):
                return

            duration = self.stats.duration_seconds
            mins, secs = divmod(int(duration), 60)
            hours, mins = divmod(mins, 60)

            embed = discord.Embed(
                title="Voxify Session Report",
                color=discord.Color.blurple(),
            )
            embed.add_field(name="Guild", value=self.guild.name, inline=True)
            embed.add_field(
                name="Duration",
                value=f"{hours}h {mins}m {secs}s",
                inline=True,
            )
            embed.add_field(
                name="Messages Processed",
                value=str(self.stats.messages_processed),
                inline=True,
            )
            embed.add_field(
                name="Audio Generated",
                value=f"{self.stats.audio_minutes:.2f} min",
                inline=True,
            )
            speakers = ", ".join(f"<@{s.user_id}>" for s in self.speakers.values())
            embed.add_field(name="Speakers", value=speakers or "None", inline=False)
            await channel.send(embed=embed)
        except Exception:
            log.exception("Failed to send session report")


class SessionManager:
    """One active session per guild."""

    def __init__(self) -> None:
        self._sessions: dict[int, TTSSession] = {}

    def get(self, guild_id: int) -> Optional[TTSSession]:
        return self._sessions.get(guild_id)

    def set(self, guild_id: int, session: TTSSession) -> None:
        self._sessions[guild_id] = session

    def remove(self, guild_id: int) -> Optional[TTSSession]:
        return self._sessions.pop(guild_id, None)

    def has(self, guild_id: int) -> bool:
        return guild_id in self._sessions


# Module-level singleton
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    return _session_manager
