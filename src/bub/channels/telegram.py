"""Telegram channel adapter."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from bub.channels.base import BaseChannel
from bub.channels.bus import MessageBus
from bub.channels.events import InboundMessage, OutboundMessage


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
        self._running = True
        self._app = Application.builder().token(self._config.token).build()
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))
        await self._app.initialize()
        await self._app.start()
        updater = self._app.updater
        if updater is None:
            return
        await updater.start_polling(drop_pending_updates=True, allowed_updates=["message"])
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

    async def send(self, message: OutboundMessage) -> None:
        if self._app is None:
            return
        self._stop_typing(message.chat_id)
        await self._app.bot.send_message(chat_id=int(message.chat_id), text=message.content)

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
        self._start_typing(chat_id)
        self.publish_inbound(
            InboundMessage(
                channel=self.name,
                sender_id=str(user.id),
                chat_id=chat_id,
                content=update.message.text or "",
                metadata={
                    "username": user.username or "",
                    "first_name": user.first_name or "",
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
            return
