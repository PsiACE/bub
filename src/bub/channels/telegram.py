"""Telegram channel adapter."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from loguru import logger
from telegram import Message, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bub.app.runtime import AppRuntime
from bub.channels.base import BaseChannel, exclude_none
from bub.channels.utils import resolve_proxy
from bub.core.agent_loop import LoopResult

NO_ACCESS_MESSAGE = "You are not allowed to chat with me. Please deploy your own instance of Bub."


def _message_type(message: Message) -> str:
    if getattr(message, "text", None):
        return "text"
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "sticker", None):
        return "sticker"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "document", None):
        return "document"
    if getattr(message, "video_note", None):
        return "video_note"
    return "unknown"


class BubMessageFilter(filters.MessageFilter):
    GROUP_CHAT_TYPES: ClassVar[set[str]] = {"group", "supergroup"}

    def _content(self, message: Message) -> str:
        return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()

    def filter(self, message: Message) -> bool | dict[str, list[Any]] | None:
        msg_type = _message_type(message)
        if msg_type == "unknown":
            return False

        # Private chat: process all non-command messages and bot commands.
        if message.chat.type == "private":
            return True

        # Group chat: only process when explicitly addressed to the bot.
        if message.chat.type in self.GROUP_CHAT_TYPES:
            bot = message.get_bot()
            bot_id = bot.id
            bot_username = (bot.username or "").lower()

            mentions_bot = self._mentions_bot(message, bot_id, bot_username)
            reply_to_bot = self._is_reply_to_bot(message, bot_id)

            if msg_type != "text" and not getattr(message, "caption", None):
                return reply_to_bot

            return mentions_bot or reply_to_bot

        return False

    def _mentions_bot(self, message: Message, bot_id: int, bot_username: str) -> bool:
        content = self._content(message).lower()
        mentions_by_keyword = "bub" in content or bool(bot_username and f"@{bot_username}" in content)

        entities = [*(getattr(message, "entities", None) or ()), *(getattr(message, "caption_entities", None) or ())]
        for entity in entities:
            if entity.type == "mention" and bot_username:
                mention_text = content[entity.offset : entity.offset + entity.length]
                if mention_text.lower() == f"@{bot_username}":
                    return True
                continue
            if entity.type == "text_mention" and entity.user and entity.user.id == bot_id:
                return True
        return mentions_by_keyword

    @staticmethod
    def _is_reply_to_bot(message: Message, bot_id: int) -> bool:
        reply_to_message = message.reply_to_message
        if reply_to_message is None or reply_to_message.from_user is None:
            return False
        return reply_to_message.from_user.id == bot_id


MESSAGE_FILTER = BubMessageFilter()


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram adapter config."""

    token: str
    allow_from: set[str]
    allow_chats: set[str]
    proxy: str | None = None


class TelegramChannel(BaseChannel[Message]):
    """Telegram adapter using long polling mode."""

    name = "telegram"

    def __init__(self, runtime: AppRuntime) -> None:
        super().__init__(runtime)
        settings = runtime.settings
        assert settings.telegram_token is not None  # noqa: S101
        self._config = TelegramConfig(
            token=settings.telegram_token,
            allow_from=set(settings.telegram_allow_from),
            allow_chats=set(settings.telegram_allow_chats),
            proxy=settings.telegram_proxy,
        )
        self._app: Application | None = None
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}
        self._on_receive: Callable[[Message], Awaitable[None]] | None = None

    async def start(self, on_receive: Callable[[Message], Awaitable[None]]) -> None:
        self._on_receive = on_receive
        proxy, _ = resolve_proxy(self._config.proxy)
        logger.info(
            "telegram.start allow_from_count={} allow_chats_count={} proxy_enabled={}",
            len(self._config.allow_from),
            len(self._config.allow_chats),
            bool(proxy),
        )
        builder = Application.builder().token(self._config.token)
        if proxy:
            builder = builder.proxy(proxy).get_updates_proxy(proxy)
        self._app = builder.build()
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("bub", self._on_text, has_args=True, block=False))
        self._app.add_handler(MessageHandler(~filters.COMMAND, self._on_text, block=False))
        await self._app.initialize()
        await self._app.start()
        updater = self._app.updater
        if updater is None:
            return
        await updater.start_polling(drop_pending_updates=True, allowed_updates=["message"])
        logger.info("telegram.polling")
        try:
            await asyncio.Event().wait()  # Keep running until stopped
        finally:
            for task in self._typing_tasks.values():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*self._typing_tasks.values())
            self._typing_tasks.clear()
            updater = self._app.updater
            with contextlib.suppress(Exception):
                if updater is not None and updater.running:
                    await updater.stop()
                await self._app.stop()
                await self._app.shutdown()
            self._app = None
            logger.info("telegram.stopped")

    async def get_session_prompt(self, message: Message) -> tuple[str, str] | None:
        if MESSAGE_FILTER.filter(message) is False:
            return None
        chat_id = str(message.chat_id)
        session_id = f"{self.name}:{chat_id}"
        content, media = self._parse_message(message)
        if content.startswith("/bub "):
            content = content[5:]

        # Pass comma commands directly to the input handler
        if content.strip().startswith(","):
            logger.info("telegram.inbound.command chat_id={} content={}", chat_id, content)
            return session_id, content

        metadata: dict[str, Any] = {
            "message_id": message.message_id,
            "type": _message_type(message),
            "username": message.from_user.username if message.from_user else "",
            "full_name": message.from_user.full_name if message.from_user else "",
            "sender_id": str(message.from_user.id) if message.from_user else "",
            "date": message.date.timestamp() if message.date else None,
        }
        logger.info(
            "telegram.inbound.message chat_id={} user_id={} username={} content={}",
            chat_id,
            metadata["sender_id"],
            metadata["username"],
            content,
        )

        if media:
            metadata["media"] = media
            caption = getattr(message, "caption", None)
            if caption:
                metadata["caption"] = caption

        reply_meta = self._extract_reply_metadata(message)
        if reply_meta:
            metadata["reply_to_message"] = reply_meta

        metadata_json = json.dumps({"channel": self.name, "chat_id": chat_id, **metadata}, ensure_ascii=False)
        prompt = f"{content}\n———————\n{metadata_json}"
        return session_id, prompt

    async def process_output(self, session_id: str, output: LoopResult) -> None:
        parts = [part for part in (output.immediate_output, output.assistant_output) if part]
        if output.error:
            parts.append(f"error: {output.error}")
        content = "\n\n".join(parts).strip()
        if not content:
            return
        logger.info("telegram.outbound session_id={} content={}", session_id, content)
        send_back_text = [output.immediate_output] if output.immediate_output else []
        if not self.runtime.settings.proactive_response:
            send_back_text.extend([output.assistant_output] if output.assistant_output else [])
        # NOTE: assistant output is ignored intentionally to rely on the telegram skill to send messages proactively.
        # Feel free to override this method to ensure response for every message received.
        if output.error:
            send_back_text.append(f"Error: {output.error}")
        if send_back_text and self._app is not None:
            await self._app.bot.send_message(chat_id=session_id.split(":", 1)[1], text="\n\n".join(send_back_text))

    async def _on_start(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if self._config.allow_chats and str(update.message.chat_id) not in self._config.allow_chats:
            await update.message.reply_text(NO_ACCESS_MESSAGE)
            return
        await update.message.reply_text("Bub is online. Send text to start.")

    async def _on_text(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None:
            return
        chat_id = str(update.message.chat_id)
        if self._config.allow_chats and chat_id not in self._config.allow_chats:
            return
        user = update.effective_user
        sender_tokens = {str(user.id)}
        if user.username:
            sender_tokens.add(user.username)
        if self._config.allow_from and sender_tokens.isdisjoint(self._config.allow_from):
            await update.message.reply_text("Access denied.")
            return

        text, _ = self._parse_message(update.message)
        if text.startswith("/bot ") or text.startswith("/bub "):
            text = text[5:]

        if self._on_receive is None:
            logger.warning("telegram.inbound no handler for received messages")
            return
        await self._start_typing(chat_id)
        try:
            await self._on_receive(update.message)
        finally:
            await self._stop_typing(chat_id)

    async def _start_typing(self, chat_id: str) -> None:
        await self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    async def _stop_typing(self, chat_id: str) -> None:
        task = self._typing_tasks.pop(chat_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _typing_loop(self, chat_id: str) -> None:
        try:
            while self._app is not None:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("telegram.typing_loop.error chat_id={}", chat_id)
            return

    @classmethod
    def _parse_message(cls, message: Message) -> tuple[str, dict[str, Any] | None]:
        msg_type = _message_type(message)
        if msg_type == "text":
            return getattr(message, "text", None) or "", None
        parser = cls._MEDIA_MESSAGE_PARSERS.get(msg_type)
        if parser is not None:
            return parser(message)
        return "[Unknown message type]", None

    @staticmethod
    def _parse_photo(message: Message) -> tuple[str, dict[str, Any] | None]:
        caption = getattr(message, "caption", None) or ""
        formatted = f"[Photo message] Caption: {caption}" if caption else "[Photo message]"
        photos = getattr(message, "photo", None) or []
        if not photos:
            return formatted, None
        largest = photos[-1]
        metadata = exclude_none({
            "file_id": largest.file_id,
            "file_size": largest.file_size,
            "width": largest.width,
            "height": largest.height,
        })
        return formatted, metadata

    @staticmethod
    def _parse_audio(message: Message) -> tuple[str, dict[str, Any] | None]:
        audio = getattr(message, "audio", None)
        if audio is None:
            return "[Audio]", None
        title = audio.title or "Unknown"
        performer = audio.performer or ""
        duration = audio.duration or 0
        metadata = exclude_none({
            "file_id": audio.file_id,
            "file_size": audio.file_size,
            "duration": audio.duration,
            "title": audio.title,
            "performer": audio.performer,
        })
        if performer:
            return f"[Audio: {performer} - {title} ({duration}s)]", metadata
        return f"[Audio: {title} ({duration}s)]", metadata

    @staticmethod
    def _parse_sticker(message: Message) -> tuple[str, dict[str, Any] | None]:
        sticker = getattr(message, "sticker", None)
        if sticker is None:
            return "[Sticker]", None
        emoji = sticker.emoji or ""
        set_name = sticker.set_name or ""
        metadata = exclude_none({
            "file_id": sticker.file_id,
            "width": sticker.width,
            "height": sticker.height,
            "emoji": sticker.emoji,
            "set_name": sticker.set_name,
            "is_animated": sticker.is_animated,
            "is_video": sticker.is_video,
        })
        if emoji:
            return f"[Sticker: {emoji} from {set_name}]", metadata
        return f"[Sticker from {set_name}]", metadata

    @staticmethod
    def _parse_video(message: Message) -> tuple[str, dict[str, Any] | None]:
        video = getattr(message, "video", None)
        duration = video.duration if video else 0
        caption = getattr(message, "caption", None) or ""
        formatted = f"[Video: {duration}s]"
        formatted = f"{formatted} Caption: {caption}" if caption else formatted
        if video is None:
            return formatted, None
        metadata = exclude_none({
            "file_id": video.file_id,
            "file_size": video.file_size,
            "width": video.width,
            "height": video.height,
            "duration": video.duration,
        })
        return formatted, metadata

    @staticmethod
    def _parse_voice(message: Message) -> tuple[str, dict[str, Any] | None]:
        voice = getattr(message, "voice", None)
        duration = voice.duration if voice else 0
        if voice is None:
            return f"[Voice message: {duration}s]", None
        metadata = exclude_none({"file_id": voice.file_id, "duration": voice.duration})
        return f"[Voice message: {duration}s]", metadata

    @staticmethod
    def _parse_document(message: Message) -> tuple[str, dict[str, Any] | None]:
        document = getattr(message, "document", None)
        if document is None:
            return "[Document]", None
        file_name = document.file_name or "unknown"
        mime_type = document.mime_type or "unknown"
        caption = getattr(message, "caption", None) or ""
        formatted = f"[Document: {file_name} ({mime_type})]"
        formatted = f"{formatted} Caption: {caption}" if caption else formatted
        metadata = exclude_none({
            "file_id": document.file_id,
            "file_name": document.file_name,
            "file_size": document.file_size,
            "mime_type": document.mime_type,
        })
        return formatted, metadata

    @staticmethod
    def _parse_video_note(message: Message) -> tuple[str, dict[str, Any] | None]:
        video_note = getattr(message, "video_note", None)
        duration = video_note.duration if video_note else 0
        if video_note is None:
            return f"[Video note: {duration}s]", None
        metadata = exclude_none({"file_id": video_note.file_id, "duration": video_note.duration})
        return f"[Video note: {duration}s]", metadata

    @staticmethod
    def _extract_reply_metadata(message: Message) -> dict[str, Any] | None:
        reply_to = message.reply_to_message
        if reply_to is None or reply_to.from_user is None:
            return None
        return exclude_none({
            "message_id": reply_to.message_id,
            "from_user_id": reply_to.from_user.id,
            "from_username": reply_to.from_user.username,
            "from_is_bot": reply_to.from_user.is_bot,
            "text": (reply_to.text or "")[:100] if reply_to.text else "",
        })

    _MEDIA_MESSAGE_PARSERS: ClassVar[dict[str, Callable[[Message], tuple[str, dict[str, Any] | None]]]] = {
        "photo": _parse_photo,
        "audio": _parse_audio,
        "sticker": _parse_sticker,
        "video": _parse_video,
        "voice": _parse_voice,
        "document": _parse_document,
        "video_note": _parse_video_note,
    }
