from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import Any, ClassVar

from loguru import logger
from pydantic import Field, json
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Message, Update
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from telegram.ext import MessageHandler as TelegramMessageHandler

from bub.channels.base import Channel
from bub.channels.message import ChannelMessage
from bub.channels.utils import exclude_none
from bub.types import MessageHandler


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BUB_TELEGRAM_", extra="ignore", env_file=".env")

    token: str = Field(default="", description="Telegram bot token.")
    allow_users: str | None = Field(
        default=None, description="Comma-separated list of allowed Telegram user IDs, or empty for no restriction."
    )
    allow_chats: str | None = Field(
        default=None, description="Comma-separated list of allowed Telegram chat IDs, or empty for no restriction."
    )
    proxy: str | None = Field(
        default=None,
        description="Optional proxy URL for connecting to Telegram API, e.g. 'http://user:pass@host:port' or 'socks5://host:port'.",
    )


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


class TelegramChannel(Channel):
    name = "telegram"
    _app: Application

    def __init__(self, on_receive: MessageHandler) -> None:
        self._on_receive = on_receive
        self._settings = TelegramSettings()
        self._allow_users = {uid.strip() for uid in (self._settings.allow_users or "").split(",") if uid.strip()}
        self._allow_chats = {cid.strip() for cid in (self._settings.allow_chats or "").split(",") if cid.strip()}
        self._parser = TelegramMessageParser()

    @property
    def needs_debounce(self) -> bool:
        return True

    async def start(self) -> None:
        proxy = self._settings.proxy
        logger.info(
            "telegram.start allow_users_count={} allow_chats_count={} proxy_enabled={}",
            len(self._allow_users),
            len(self._allow_chats),
            bool(proxy),
        )
        builder = Application.builder().token(self._settings.token)
        if proxy:
            builder = builder.proxy(proxy).get_updates_proxy(proxy)
        self._app = builder.build()
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("bub", self._on_message, has_args=True, block=False))
        self._app.add_handler(TelegramMessageHandler(~filters.COMMAND, self._on_message, block=False))
        await self._app.initialize()
        await self._app.start()
        updater = self._app.updater
        if updater is None:
            return
        await updater.start_polling(drop_pending_updates=True, allowed_updates=["message"])
        logger.info("telegram.start polling")

    async def stop(self) -> None:
        updater = self._app.updater
        with contextlib.suppress(Exception):
            if updater is not None and updater.running:
                await updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        logger.info("telegram.stopped")

    async def send(self, message: ChannelMessage) -> None:
        chat_id = message.chat_id
        content = message.content
        try:
            data = json.loads(content)
            text = data.get("message", "")
        except json.JSONDecodeError:
            text = content
        if not text.strip():
            return
        await self._app.bot.send_message(chat_id=chat_id, text=text)

    async def _on_start(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if self._allow_chats and str(update.message.chat_id) not in self._allow_chats:
            await update.message.reply_text(NO_ACCESS_MESSAGE)
            return
        await update.message.reply_text("Bub is online. Send text to start.")

    async def _on_message(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None:
            return
        chat_id = str(update.message.chat_id)
        if self._allow_chats and chat_id not in self._allow_chats:
            return
        user = update.effective_user
        sender_tokens = {str(user.id)}
        if user.username:
            sender_tokens.add(user.username)
        if self._allow_users and sender_tokens.isdisjoint(self._allow_users):
            await update.message.reply_text("Access denied.")
            return
        await self._on_receive(self._build_message(update.message))

    def _build_message(self, message: Message) -> ChannelMessage:
        chat_id = str(message.chat_id)
        session_id = f"{self.name}:{chat_id}"
        content, metadata = self._parser.parse(message)
        if content.startswith("/bub "):
            content = content[5:]

        # Pass comma commands directly to the input handler
        if content.strip().startswith(","):
            return ChannelMessage(session_id=session_id, content=content.strip(), channel=self.name, chat_id=chat_id)

        reply_meta = self._parser.get_reply(message)
        if reply_meta:
            metadata["reply_to_message"] = reply_meta

        content = json.dumps({"message": content, "chat_id": chat_id, **metadata}, ensure_ascii=False)
        is_active = MESSAGE_FILTER.filter(message) is not False
        return ChannelMessage(
            session_id=session_id,
            channel=self.name,
            chat_id=chat_id,
            content=content,
            is_active=is_active,
        )


class TelegramMessageParser:
    @classmethod
    def parse(cls, message: Message) -> tuple[str, dict[str, Any]]:
        msg_type = _message_type(message)
        content, media = f"[Unsupported message type: {msg_type}]", None
        if msg_type == "text":
            content, media = getattr(message, "text", None) or "", None
        else:
            parser = cls._MEDIA_MESSAGE_PARSERS.get(msg_type)
            if parser is not None:
                content, media = parser(message)
        metadata = exclude_none({
            "message_id": message.message_id,
            "type": _message_type(message),
            "username": message.from_user.username if message.from_user else "",
            "full_name": message.from_user.full_name if message.from_user else "",
            "sender_id": str(message.from_user.id) if message.from_user else "",
            "sender_is_bot": message.from_user.is_bot if message.from_user else None,
            "date": message.date.timestamp() if message.date else None,
            "media": media,
            "caption": getattr(message, "caption", None),
        })
        return content, metadata

    @classmethod
    def get_reply(cls, message: Message) -> dict[str, Any] | None:
        reply_to = message.reply_to_message
        if reply_to is None or reply_to.from_user is None:
            return None
        content, metadata = cls.parse(reply_to)
        return {"message": content, **metadata}

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

    _MEDIA_MESSAGE_PARSERS: ClassVar[dict[str, Callable[[Message], tuple[str, dict[str, Any] | None]]]] = {
        "photo": _parse_photo,
        "audio": _parse_audio,
        "sticker": _parse_sticker,
        "video": _parse_video,
        "voice": _parse_voice,
        "document": _parse_document,
        "video_note": _parse_video_note,
    }
