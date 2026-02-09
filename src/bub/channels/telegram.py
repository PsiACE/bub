"""Telegram channel adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, ClassVar

from loguru import logger
from telegram import Message, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegramify_markdown import markdownify as md

from bub.channels.base import BaseChannel
from bub.channels.bus import MessageBus
from bub.channels.events import InboundMessage, OutboundMessage


class BubMessageFilter(filters.MessageFilter):
    GROUP_CHAT_TYPES: ClassVar[set[str]] = {"group", "supergroup"}

    def filter(self, message: Message) -> bool | dict[str, list[Any]] | None:
        # Only text messages are allowed
        text = message.text
        if not text:
            return False

        # Private chat: accept all messages except for commands (starting with /)
        if message.chat.type == "private":
            return not filters.COMMAND.filter(message)

        # Group chat: only allow `/bot`, mention bot, or reply to bot messages.
        if message.chat.type in self.GROUP_CHAT_TYPES:
            bot = message.get_bot()
            bot_id = bot.id
            bot_username = (bot.username or "").lower()
            if text.startswith("/bot "):
                return True

            if self._mentions_bot(message, text, bot_id, bot_username):
                return True

            if self._is_reply_to_bot(message, bot_id):
                return True

        return False

    @staticmethod
    def _mentions_bot(message: Message, text: str, bot_id: int, bot_username: str) -> bool:
        for entity in message.entities or ():
            if entity.type == "mention" and bot_username:
                mention_text = text[entity.offset : entity.offset + entity.length]
                if mention_text.lower() == f"@{bot_username}":
                    return True
                continue
            if entity.type == "text_mention" and entity.user and entity.user.id == bot_id:
                return True
        return False

    @staticmethod
    def _is_reply_to_bot(message: Message, bot_id: int) -> bool:
        reply_to_message = message.reply_to_message
        if reply_to_message is None or reply_to_message.from_user is None:
            return False
        return reply_to_message.from_user.id == bot_id


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram adapter config."""

    token: str
    allow_from: set[str]


class TelegramChannel(BaseChannel):
    """Telegram adapter using long polling mode."""

    name = "telegram"

    def __init__(self, bus: MessageBus, config: TelegramConfig) -> None:
        super().__init__(bus)
        self._config = config
        self._app: Application | None = None
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}

    async def start(self) -> None:
        if not self._config.token:
            raise RuntimeError("telegram token is empty")
        logger.info("telegram.channel.start allow_from_count={}", len(self._config.allow_from))
        self._running = True
        self._app = Application.builder().token(self._config.token).build()
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(MessageHandler(BubMessageFilter(), self._on_text, block=False))
        await self._app.initialize()
        await self._app.start()
        updater = self._app.updater
        if updater is None:
            return
        await updater.start_polling(drop_pending_updates=True, allowed_updates=["message"])
        logger.info("telegram.channel.polling")
        while self._running:
            await asyncio.sleep(0.5)

    async def stop(self) -> None:
        self._running = False
        for task in self._typing_tasks.values():
            task.cancel()
        self._typing_tasks.clear()
        if self._app is None:
            return
        updater = self._app.updater
        if updater is not None:
            await updater.stop()
        await self._app.stop()
        await self._app.shutdown()
        self._app = None
        logger.info("telegram.channel.stopped")

    async def send(self, message: OutboundMessage) -> None:
        if self._app is None:
            return
        self._stop_typing(message.chat_id)

        text = md(message.content)

        # Use expandable blockquote for long messages
        MAX_MESSAGE_LENGTH = 4000
        if len(text.encode("utf-8")) > MAX_MESSAGE_LENGTH:
            # Wrap long message in expandable blockquote
            text = f"<blockquote expandable>{text}</blockquote>"
            parse_mode = "HTML"
        else:
            parse_mode = "MarkdownV2"

        # In group chats, reply to the original message if reply_to_message_id is provided
        if message.reply_to_message_id is not None:
            await self._app.bot.send_message(
                chat_id=int(message.chat_id),
                text=text,
                parse_mode=parse_mode,
                reply_to_message_id=message.reply_to_message_id,
            )
        else:
            await self._app.bot.send_message(
                chat_id=int(message.chat_id),
                text=text,
                parse_mode=parse_mode,
            )

    async def _on_start(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        await update.message.reply_text("Bub is online. Send text to start.")

    async def _on_help(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        await update.message.reply_text(
            "Commands:\n"
            "/start - show startup message\n"
            "/help - show this help\n\n"
            "All plain text is routed to Bub runtime."
        )

    async def _on_text(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None or update.effective_user is None:
            return
        user = update.effective_user
        sender_tokens = {str(user.id)}
        if user.username:
            sender_tokens.add(user.username)
        if self._config.allow_from and sender_tokens.isdisjoint(self._config.allow_from):
            await update.message.reply_text("Access denied.")
            return

        chat_id = str(update.message.chat_id)
        text = update.message.text or ""
        # Strip /bot prefix if present
        if text.startswith("/bot "):
            text = text[5:]

        logger.info(
            "telegram.channel.inbound chat_id={} sender_id={} username={} content={}",
            chat_id,
            user.id,
            user.username or "",
            text[:100],  # Log first 100 chars to avoid verbose logs
        )

        self._start_typing(chat_id)
        await self.publish_inbound(
            InboundMessage(
                channel=self.name,
                sender_id=str(user.id),
                chat_id=chat_id,
                content=text,
                metadata={
                    "username": user.username or "",
                    "first_name": user.first_name or "",
                    "message_id": update.message.message_id,
                },
            )
        )

    def _start_typing(self, chat_id: str) -> None:
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))

    def _stop_typing(self, chat_id: str) -> None:
        task = self._typing_tasks.pop(chat_id, None)
        if task is not None:
            task.cancel()

    async def _typing_loop(self, chat_id: str) -> None:
        try:
            while self._app is not None:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("telegram.channel.typing_loop.error chat_id={}", chat_id)
            return
