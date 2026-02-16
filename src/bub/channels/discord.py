"""Discord channel adapter."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

import discord
from discord.ext import commands
from loguru import logger

from bub.app.runtime import AppRuntime
from bub.channels.base import BaseChannel, exclude_none
from bub.channels.utils import resolve_proxy
from bub.core.agent_loop import LoopResult


def _message_type(message: discord.Message) -> str:
    if message.content:
        return "text"
    if message.attachments:
        return "attachment"
    if message.stickers:
        return "sticker"
    return "unknown"


@dataclass(frozen=True)
class DiscordConfig:
    """Discord adapter config."""

    token: str
    allow_from: set[str]
    allow_channels: set[str]
    command_prefix: str = "!"
    proxy: str | None = None


class DiscordChannel(BaseChannel[discord.Message]):
    """Discord adapter based on discord.py."""

    name = "discord"

    def __init__(self, runtime: AppRuntime) -> None:
        super().__init__(runtime)
        settings = runtime.settings
        self._config = DiscordConfig(
            token=settings.discord_token or "",
            allow_from=set(settings.discord_allow_from),
            allow_channels=set(settings.discord_allow_channels),
            command_prefix=settings.discord_command_prefix,
            proxy=settings.discord_proxy,
        )
        self._bot: commands.Bot | None = None
        self._on_receive: Callable[[discord.Message], Awaitable[None]] | None = None
        self._latest_message_by_session: dict[str, discord.Message] = {}

    async def start(self, on_receive: Callable[[discord.Message], Awaitable[None]]) -> None:
        if not self._config.token:
            raise RuntimeError("discord token is empty")

        self._on_receive = on_receive
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True

        proxy, _ = resolve_proxy(self._config.proxy)
        bot = commands.Bot(command_prefix=self._config.command_prefix, intents=intents, help_command=None, proxy=proxy)
        self._bot = bot

        @bot.event
        async def on_ready() -> None:
            logger.info("discord.ready user={} id={}", str(bot.user), bot.user.id if bot.user else "<unknown>")

        @bot.event
        async def on_message(message: discord.Message) -> None:
            await bot.process_commands(message)
            await self._on_message(message)

        logger.info(
            "discord.start allow_from_count={} allow_channels_count={} proxy_enabled={}",
            len(self._config.allow_from),
            len(self._config.allow_channels),
            bool(proxy),
        )
        try:
            async with bot:
                await bot.start(self._config.token)
        finally:
            self._bot = None
            logger.info("discord.stopped")

    async def get_session_prompt(self, message: discord.Message) -> tuple[str, str] | None:
        channel_id = str(message.channel.id)
        session_id = f"{self.name}:{channel_id}"
        content, media = self._parse_message(message)

        prefix = f"{self._config.command_prefix}bub "
        if content.startswith(prefix):
            content = content[len(prefix) :]

        if content.strip().startswith(","):
            self._latest_message_by_session[session_id] = message
            return session_id, content

        metadata: dict[str, Any] = {
            "message_id": message.id,
            "type": _message_type(message),
            "username": message.author.name,
            "full_name": getattr(message.author, "display_name", message.author.name),
            "sender_id": str(message.author.id),
            "date": message.created_at.timestamp() if message.created_at else None,
            "channel_id": str(message.channel.id),
            "guild_id": str(message.guild.id) if message.guild else None,
        }

        if media:
            metadata["media"] = media

        reply_meta = self._extract_reply_metadata(message)
        if reply_meta:
            metadata["reply_to_message"] = reply_meta

        metadata_json = json.dumps(
            {"channel": "discord", "channel_id": channel_id, **exclude_none(metadata)}, ensure_ascii=False
        )
        prompt = (
            "IMPORTANT: Please reply to this $discord message unless otherwise instructed.\n\n"
            f"{content}\n———————\n{metadata_json}"
        )
        self._latest_message_by_session[session_id] = message
        return session_id, prompt

    async def process_output(self, session_id: str, output: LoopResult) -> None:
        parts = [part for part in (output.immediate_output, output.assistant_output) if part]
        if output.error:
            parts.append(f"Error: {output.error}")
        content = "\n\n".join(parts).strip()
        if content:
            print(content, flush=True)

        send_content = output.immediate_output.strip()
        if not send_content:
            return

        channel = await self._resolve_channel(session_id)
        if channel is None:
            logger.warning("discord.outbound unresolved channel session_id={}", session_id)
            return

        source = self._latest_message_by_session.get(session_id)
        reference = source.to_reference(fail_if_not_exists=False) if source is not None else None
        for chunk in self._chunk_message(send_content):
            kwargs: dict[str, Any] = {"content": chunk}
            if reference is not None:
                kwargs["reference"] = reference
                kwargs["mention_author"] = False
            await channel.send(**kwargs)

    async def _on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not self._allow_message(message):
            return
        if self._on_receive is None:
            logger.warning("discord.inbound no handler for received messages")
            return

        content, _ = self._parse_message(message)
        logger.info(
            "discord.inbound channel_id={} sender_id={} username={} content={}",
            message.channel.id,
            message.author.id,
            message.author.name,
            content[:100],
        )

        async with message.channel.typing():
            await self._on_receive(message)

    async def _resolve_channel(self, session_id: str) -> discord.abc.Messageable | None:
        if self._bot is None:
            return None
        channel_id = int(session_id.split(":", 1)[1])
        channel = self._bot.get_channel(channel_id)
        if channel is not None:
            return channel  # type: ignore[return-value]
        with contextlib.suppress(Exception):
            fetched = await self._bot.fetch_channel(channel_id)
            if isinstance(fetched, discord.abc.Messageable):
                return fetched
        return None

    def _allow_message(self, message: discord.Message) -> bool:
        channel_id = str(message.channel.id)
        if self._config.allow_channels and channel_id not in self._config.allow_channels:
            return False

        if not message.content.strip():
            return False

        sender_tokens = {str(message.author.id), message.author.name}
        if getattr(message.author, "global_name", None):
            sender_tokens.add(cast(str, message.author.global_name))
        if self._config.allow_from and sender_tokens.isdisjoint(self._config.allow_from):
            logger.warning(
                "discord.inbound.denied channel_id={} sender_id={} reason=allow_from",
                message.channel.id,
                message.author.id,
            )
            return False

        if (
            isinstance(message.channel, discord.DMChannel)
            or "bub" in message.content.lower()
            or self._is_bub_scoped_thread(message)
            or message.content.startswith(f"{self._config.command_prefix}bub")
        ):
            return True

        bot_user = self._bot.user if self._bot is not None else None
        if bot_user is None:
            return False
        if bot_user in message.mentions:
            return True

        ref = message.reference
        if ref is None:
            return False
        resolved = ref.resolved
        return bool(isinstance(resolved, discord.Message) and resolved.author and resolved.author.id == bot_user.id)

    @staticmethod
    def _is_bub_scoped_thread(message: discord.Message) -> bool:
        channel = message.channel
        thread_name = getattr(channel, "name", None)
        if not isinstance(thread_name, str):
            return False
        is_thread = isinstance(channel, discord.Thread) or getattr(channel, "parent", None) is not None
        return is_thread and thread_name.lower().startswith("bub")

    @staticmethod
    def _parse_message(message: discord.Message) -> tuple[str, dict[str, Any] | None]:
        if message.content:
            return message.content, None

        if message.attachments:
            attachment_lines: list[str] = []
            attachment_meta: list[dict[str, Any]] = []
            for att in message.attachments:
                attachment_lines.append(f"[Attachment: {att.filename}]")
                attachment_meta.append(
                    exclude_none({
                        "id": str(att.id),
                        "filename": att.filename,
                        "content_type": att.content_type,
                        "size": att.size,
                        "url": att.url,
                    })
                )
            return "\n".join(attachment_lines), {"attachments": attachment_meta}

        if message.stickers:
            lines = [f"[Sticker: {sticker.name}]" for sticker in message.stickers]
            meta = [{"id": str(sticker.id), "name": sticker.name} for sticker in message.stickers]
            return "\n".join(lines), {"stickers": meta}

        return "[Unknown message type]", None

    @staticmethod
    def _extract_reply_metadata(message: discord.Message) -> dict[str, Any] | None:
        ref = message.reference
        if ref is None:
            return None
        resolved = ref.resolved
        if not isinstance(resolved, discord.Message):
            return None
        return exclude_none({
            "message_id": str(resolved.id),
            "from_user_id": str(resolved.author.id),
            "from_username": resolved.author.name,
            "from_is_bot": resolved.author.bot,
            "text": (resolved.content or "")[:100],
        })

    @staticmethod
    def _chunk_message(text: str, *, limit: int = 2000) -> list[str]:
        if len(text) <= limit:
            return [text]
        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, limit)
            if split_at <= 0:
                split_at = limit
            chunks.append(remaining[:split_at].rstrip())
            remaining = remaining[split_at:].lstrip("\n")
        return [chunk for chunk in chunks if chunk]
