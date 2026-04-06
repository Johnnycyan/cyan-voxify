from __future__ import annotations

import discord
from discord import SlashCommandGroup, option
from discord.ext import commands

from bot.db import queries
from bot.utils.permissions import has_manage_guild, is_admin


class Settings(commands.Cog):
    def __init__(self, bot: discord.Bot) -> None:
        self.bot = bot

    # ── top-level group ────────────────────────────────────────────────────
    config = SlashCommandGroup("config", "Bot configuration commands")
    config_global = config.create_subgroup("global", "Global bot settings")
    config_guild = config.create_subgroup("guild", "Per-guild settings")

    # ── helpers ────────────────────────────────────────────────────────────

    async def _require_admin(self, ctx: discord.ApplicationContext) -> bool:
        if await is_admin(ctx.author.id):
            return True
        await ctx.respond("Only the bot admin can use this command.", ephemeral=True)
        return False

    async def _require_guild_manager(self, ctx: discord.ApplicationContext) -> bool:
        if await is_admin(ctx.author.id):
            return True
        if isinstance(ctx.author, discord.Member) and has_manage_guild(ctx.author):
            return True
        await ctx.respond(
            "You need the **Manage Server** permission or be the bot admin.",
            ephemeral=True,
        )
        return False

    # =====================================================================
    # GLOBAL COMMANDS
    # =====================================================================

    @config_global.command(name="admin", description="Set the bot admin user")
    @option("user", discord.User, description="User to make the bot admin")
    async def global_admin(
        self, ctx: discord.ApplicationContext, user: discord.User
    ) -> None:
        gs = await queries.get_global_settings()
        # Bootstrap: if no admin is set yet, the caller becomes admin
        if gs.admin_user_id is not None:
            if not await self._require_admin(ctx):
                return

        await queries.set_admin(str(user.id))
        await ctx.respond(f"Bot admin set to {user.mention}.", ephemeral=True)

    @config_global.command(name="apikey", description="Set the Mistral API key")
    @option("key", str, description="Your Mistral API key")
    async def global_apikey(self, ctx: discord.ApplicationContext, key: str) -> None:
        if not await self._require_admin(ctx):
            return
        await queries.set_api_key(key)
        await ctx.respond("Mistral API key saved. ✅", ephemeral=True)

    @config_global.command(
        name="idle-timeout",
        description="Set the global maximum idle timeout (seconds). Use 0 to clear.",
    )
    @option("seconds", int, description="Timeout in seconds (0 to clear)")
    async def global_idle_timeout(
        self, ctx: discord.ApplicationContext, seconds: int
    ) -> None:
        if not await self._require_admin(ctx):
            return
        value = seconds if seconds > 0 else None
        await queries.set_global_idle_timeout(value)
        if value:
            await ctx.respond(
                f"Global idle timeout set to **{value}s**.", ephemeral=True
            )
        else:
            await ctx.respond("Global idle timeout cleared.", ephemeral=True)

    @config_global.command(
        name="report", description="Configure end-of-session reports"
    )
    @option("enabled", bool, description="Enable or disable session reports")
    @option(
        "guild_id",
        str,
        description="Guild ID where reports are sent",
        required=False,
    )
    @option(
        "channel_id",
        str,
        description="Channel ID where reports are sent",
        required=False,
    )
    async def global_report(
        self,
        ctx: discord.ApplicationContext,
        enabled: bool,
        guild_id: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        if not await self._require_admin(ctx):
            return

        if enabled and (not guild_id or not channel_id):
            await ctx.respond(
                "You must provide both `guild_id` and `channel_id` when enabling reports.",
                ephemeral=True,
            )
            return

        await queries.set_session_report(enabled, guild_id, channel_id)
        state = "enabled" if enabled else "disabled"
        await ctx.respond(f"Session reports **{state}**.", ephemeral=True)

    @config_global.command(name="show", description="Show current global settings")
    async def global_show(self, ctx: discord.ApplicationContext) -> None:
        if not await self._require_admin(ctx):
            return

        gs = await queries.get_global_settings()
        key_status = "••••set" if gs.mistral_api_key_enc else "**not set**"
        admin_mention = f"<@{gs.admin_user_id}>" if gs.admin_user_id else "not set"
        timeout = f"{gs.idle_timeout_seconds}s" if gs.idle_timeout_seconds else "none"
        report = "enabled" if gs.session_report_enabled else "disabled"

        embed = discord.Embed(title="Global Settings", color=discord.Color.blurple())
        embed.add_field(name="Admin", value=admin_mention, inline=True)
        embed.add_field(name="API Key", value=key_status, inline=True)
        embed.add_field(name="Idle Timeout", value=timeout, inline=True)
        embed.add_field(name="Session Reports", value=report, inline=True)
        if gs.session_report_enabled:
            embed.add_field(
                name="Report Destination",
                value=f"Guild `{gs.report_guild_id}` / Channel `{gs.report_channel_id}`",
                inline=False,
            )
        await ctx.respond(embed=embed, ephemeral=True)

    # =====================================================================
    # GUILD COMMANDS
    # =====================================================================

    @config_guild.command(name="add-speaker", description="Add a user–voice mapping")
    @option("user", discord.User, description="Discord user")
    @option("voice_id", str, description="Voxtral voice ID for this user")
    async def guild_add_speaker(
        self,
        ctx: discord.ApplicationContext,
        user: discord.User,
        voice_id: str,
    ) -> None:
        if not await self._require_guild_manager(ctx):
            return
        await queries.add_speaker(str(ctx.guild_id), str(user.id), voice_id)
        await ctx.respond(
            f"Speaker {user.mention} added with voice `{voice_id}`.",
            ephemeral=True,
        )

    @config_guild.command(
        name="remove-speaker", description="Remove a user–voice mapping"
    )
    @option("user", discord.User, description="Discord user to remove")
    async def guild_remove_speaker(
        self, ctx: discord.ApplicationContext, user: discord.User
    ) -> None:
        if not await self._require_guild_manager(ctx):
            return
        removed = await queries.remove_speaker(str(ctx.guild_id), str(user.id))
        if removed:
            await ctx.respond(f"Speaker {user.mention} removed.", ephemeral=True)
        else:
            await ctx.respond("That user is not a configured speaker.", ephemeral=True)

    @config_guild.command(name="list-speakers", description="List configured speakers")
    async def guild_list_speakers(self, ctx: discord.ApplicationContext) -> None:
        if not await self._require_guild_manager(ctx):
            return
        speakers = await queries.get_speakers(str(ctx.guild_id))
        if not speakers:
            await ctx.respond("No speakers configured.", ephemeral=True)
            return

        lines = [f"• <@{s.user_id}> → `{s.voice_id}`" for s in speakers]
        await ctx.respond("\n".join(lines), ephemeral=True)

    @config_guild.command(
        name="whitelist-add", description="Add a channel to the whitelist"
    )
    @option("channel", discord.TextChannel, description="Channel to whitelist")
    async def guild_whitelist_add(
        self, ctx: discord.ApplicationContext, channel: discord.TextChannel
    ) -> None:
        if not await self._require_guild_manager(ctx):
            return
        current = await queries.get_channel_whitelist(str(ctx.guild_id))
        cid = str(channel.id)
        if cid not in current:
            current.append(cid)
            await queries.set_channel_whitelist(str(ctx.guild_id), current)
        await ctx.respond(
            f"Channel {channel.mention} added to whitelist.", ephemeral=True
        )

    @config_guild.command(
        name="whitelist-remove", description="Remove a channel from the whitelist"
    )
    @option("channel", discord.TextChannel, description="Channel to remove")
    async def guild_whitelist_remove(
        self, ctx: discord.ApplicationContext, channel: discord.TextChannel
    ) -> None:
        if not await self._require_guild_manager(ctx):
            return
        current = await queries.get_channel_whitelist(str(ctx.guild_id))
        cid = str(channel.id)
        if cid in current:
            current.remove(cid)
            await queries.set_channel_whitelist(str(ctx.guild_id), current)
            await ctx.respond(
                f"Channel {channel.mention} removed from whitelist.", ephemeral=True
            )
        else:
            await ctx.respond("That channel is not in the whitelist.", ephemeral=True)

    @config_guild.command(
        name="whitelist-clear", description="Clear the channel whitelist (allow all)"
    )
    async def guild_whitelist_clear(self, ctx: discord.ApplicationContext) -> None:
        if not await self._require_guild_manager(ctx):
            return
        await queries.set_channel_whitelist(str(ctx.guild_id), [])
        await ctx.respond(
            "Channel whitelist cleared — all channels allowed.", ephemeral=True
        )

    @config_guild.command(
        name="whitelist-show", description="Show the current channel whitelist"
    )
    async def guild_whitelist_show(self, ctx: discord.ApplicationContext) -> None:
        if not await self._require_guild_manager(ctx):
            return
        current = await queries.get_channel_whitelist(str(ctx.guild_id))
        if not current:
            await ctx.respond(
                "No whitelist set — all channels allowed.", ephemeral=True
            )
        else:
            mentions = [f"<#{cid}>" for cid in current]
            await ctx.respond(
                "Whitelisted channels: " + ", ".join(mentions), ephemeral=True
            )

    @config_guild.command(
        name="idle-timeout",
        description="Set the guild idle timeout (seconds). Use 0 to clear.",
    )
    @option("seconds", int, description="Timeout in seconds (0 to clear)")
    async def guild_idle_timeout(
        self, ctx: discord.ApplicationContext, seconds: int
    ) -> None:
        if not await self._require_guild_manager(ctx):
            return
        value = seconds if seconds > 0 else None
        await queries.set_guild_idle_timeout(str(ctx.guild_id), value)
        if value:
            await ctx.respond(
                f"Guild idle timeout set to **{value}s**.", ephemeral=True
            )
        else:
            await ctx.respond("Guild idle timeout cleared.", ephemeral=True)

    @config_guild.command(
        name="af-set",
        description="Set a custom FFmpeg -af filter for a voice ID",
    )
    @option("voice_id", str, description="Voxtral voice ID to apply the filter to")
    @option(
        "filter",
        str,
        description="FFmpeg audio filter string (e.g. volume=-6dB,highpass=f=120)",
    )
    async def guild_af_set(
        self,
        ctx: discord.ApplicationContext,
        voice_id: str,
        filter: str,
    ) -> None:
        if not await self._require_guild_manager(ctx):
            return
        await queries.set_voice_af_filter(str(ctx.guild_id), voice_id, filter)
        await ctx.respond(f"AF filter set for voice `{voice_id}`.", ephemeral=True)

    @config_guild.command(
        name="af-remove",
        description="Remove the FFmpeg -af filter for a voice ID",
    )
    @option("voice_id", str, description="Voxtral voice ID to remove the filter from")
    async def guild_af_remove(
        self,
        ctx: discord.ApplicationContext,
        voice_id: str,
    ) -> None:
        if not await self._require_guild_manager(ctx):
            return
        removed = await queries.remove_voice_af_filter(str(ctx.guild_id), voice_id)
        if removed:
            await ctx.respond(
                f"AF filter removed for voice `{voice_id}`.", ephemeral=True
            )
        else:
            await ctx.respond(
                f"No AF filter found for voice `{voice_id}`.", ephemeral=True
            )

    @config_guild.command(
        name="af-list",
        description="List all configured AF filters for this guild",
    )
    async def guild_af_list(self, ctx: discord.ApplicationContext) -> None:
        if not await self._require_guild_manager(ctx):
            return
        filters = await queries.get_all_voice_af_filters(str(ctx.guild_id))
        if not filters:
            await ctx.respond("No AF filters configured.", ephemeral=True)
            return
        lines = [f"• `{f.voice_id}` → `{f.af_filter}`" for f in filters]
        await ctx.respond("\n".join(lines), ephemeral=True)


def setup(bot: discord.Bot) -> None:
    bot.add_cog(Settings(bot))
