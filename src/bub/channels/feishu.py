"""Feishu channel adapter."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import threading
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from loguru import logger

from bub.app.runtime import AppRuntime
from bub.channels.base import BaseChannel, exclude_none
from bub.core.agent_loop import LoopResult

try:
    import lark_oapi as lark
    from lark_oapi.api.im.v1 import (
        CreateMessageRequest,
        CreateMessageRequestBody,
        ReplyMessageRequest,
        ReplyMessageRequestBody,
    )
except Exception:  # pragma: no cover - optional dependency during local dev
    lark = None
    CreateMessageRequest = Any
    CreateMessageRequestBody = Any
    ReplyMessageRequest = Any
    ReplyMessageRequestBody = Any


def _normalize_text(message_type: str, content: str) -> str:
    if not content:
        return ""
    parsed: dict[str, Any] | None = None
    with contextlib.suppress(json.JSONDecodeError):
        maybe_dict = json.loads(content)
        if isinstance(maybe_dict, dict):
            parsed = maybe_dict

    if message_type == "text":
        if parsed is not None:
            return str(parsed.get("text", "")).strip()
        return content.strip()
    if parsed is None:
        return f"[{message_type} message]"
    return f"[{message_type} message] {json.dumps(parsed, ensure_ascii=False)}"


@dataclass(frozen=True)
class FeishuConfig:
    """Feishu adapter config."""

    app_id: str
    app_secret: str
    verification_token: str
    encrypt_key: str
    allow_from: set[str]
    allow_chats: set[str]
    bot_open_id: str | None = None
    log_level: str = "INFO"


@dataclass(frozen=True)
class FeishuMention:
    open_id: str | None
    name: str | None
    key: str | None


@dataclass(frozen=True)
class FeishuMessage:
    message_id: str
    chat_id: str
    chat_type: str
    message_type: str
    raw_content: str
    text: str
    mentions: tuple[FeishuMention, ...]
    parent_id: str | None
    root_id: str | None
    sender_id: str | None
    sender_open_id: str | None
    sender_union_id: str | None
    sender_user_id: str | None
    sender_type: str | None
    tenant_key: str | None
    create_time: str | None
    event_type: str | None
    raw_event: dict[str, Any]


class FeishuChannel(BaseChannel[FeishuMessage]):
    """Feishu adapter using Lark websocket subscription."""

    name = "feishu"

    def __init__(self, runtime: AppRuntime) -> None:
        super().__init__(runtime)
        settings = runtime.settings
        self._config = FeishuConfig(
            app_id=getattr(settings, "feishu_app_id", "") or "",
            app_secret=getattr(settings, "feishu_app_secret", "") or "",
            verification_token=getattr(settings, "feishu_verification_token", "") or "",
            encrypt_key=getattr(settings, "feishu_encrypt_key", "") or "",
            allow_from=set(getattr(settings, "feishu_allow_from", [])),
            allow_chats=set(getattr(settings, "feishu_allow_chats", [])),
            bot_open_id=getattr(settings, "feishu_bot_open_id", None),
            log_level=(getattr(settings, "feishu_log_level", "INFO") or "INFO").upper(),
        )
        self._api_client: Any | None = None
        self._ws_client: Any | None = None
        self._ws_thread: threading.Thread | None = None
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._ws_started = threading.Event()
        self._ws_stop_requested = threading.Event()
        self._on_receive: Callable[[FeishuMessage], Awaitable[None]] | None = None
        self._main_loop: asyncio.AbstractEventLoop | None = None
        self._latest_message_by_session: dict[str, FeishuMessage] = {}
        self._bot_message_ids: set[str] = set()

    async def start(self, on_receive: Callable[[FeishuMessage], Awaitable[None]]) -> None:
        if lark is None:
            raise RuntimeError("lark-oapi is required for Feishu channel")
        if not self._config.app_id or not self._config.app_secret:
            raise RuntimeError("feishu app_id/app_secret is empty")

        self._main_loop = asyncio.get_running_loop()
        self._on_receive = on_receive
        self._api_client = (
            lark.Client.builder()
            .app_id(self._config.app_id)
            .app_secret(self._config.app_secret)
            .log_level(getattr(lark.LogLevel, self._config.log_level, lark.LogLevel.INFO))
            .build()
        )

        event_handler = (
            lark.EventDispatcherHandler.builder(self._config.verification_token, self._config.encrypt_key)
            .register_p2_im_message_receive_v1(self._on_message_event)
            .build()
        )
        self._ws_client = lark.ws.Client(
            self._config.app_id,
            self._config.app_secret,
            event_handler=event_handler,
            log_level=getattr(lark.LogLevel, self._config.log_level, lark.LogLevel.INFO),
        )

        logger.info(
            "feishu.start allow_from_count={} allow_chats_count={} bot_open_id_set={}",
            len(self._config.allow_from),
            len(self._config.allow_chats),
            bool(self._config.bot_open_id),
        )
        self._ws_stop_requested.clear()
        self._ws_started.clear()
        self._ws_thread = threading.Thread(target=self._run_ws_client, name="bub-feishu-ws", daemon=True)
        self._ws_thread.start()

        while not self._ws_started.is_set():
            await asyncio.sleep(0.05)

        try:
            await asyncio.Event().wait()
        finally:
            await self._shutdown_ws()
            logger.info("feishu.stopped")

    def is_mentioned(self, message: FeishuMessage) -> bool:
        text = message.text.strip()
        if text.startswith(","):
            return True
        if message.chat_type == "p2p":
            return True
        if message.parent_id and message.parent_id in self._bot_message_ids:
            return True
        if message.root_id and message.root_id in self._bot_message_ids:
            return True
        if "bub" in text.lower():
            return True
        if self._config.bot_open_id and any(m.open_id == self._config.bot_open_id for m in message.mentions):
            return True
        return any("bub" in (m.name or "").lower() for m in message.mentions)

    async def get_session_prompt(self, message: FeishuMessage) -> tuple[str, str]:
        session_id = f"{self.name}:{message.chat_id}"
        self._latest_message_by_session[session_id] = message

        if message.text.strip().startswith(","):
            return session_id, message.text.strip()

        payload = exclude_none({
            "message": message.text,
            "chat_id": message.chat_id,
            "chat_type": message.chat_type,
            "message_id": message.message_id,
            "message_type": message.message_type,
            "sender_id": message.sender_id,
            "sender_open_id": message.sender_open_id,
            "sender_union_id": message.sender_union_id,
            "sender_user_id": message.sender_user_id,
            "sender_type": message.sender_type,
            "tenant_key": message.tenant_key,
            "create_time": message.create_time,
            "parent_id": message.parent_id,
            "root_id": message.root_id,
            "mentions": [exclude_none({"open_id": m.open_id, "name": m.name, "key": m.key}) for m in message.mentions],
            "raw_content": message.raw_content,
            "event_type": message.event_type,
        })
        return session_id, json.dumps(payload, ensure_ascii=False)

    async def process_output(self, session_id: str, output: LoopResult) -> None:
        to_send: list[str] = []
        immediate = output.immediate_output.strip()
        assistant = output.assistant_output.strip()
        if immediate:
            to_send.append(immediate)
        if assistant and not self.runtime.settings.proactive_response:
            to_send.append(assistant)
        if output.error:
            to_send.append(f"Error: {output.error}")

        if not to_send:
            return
        content = "\n\n".join(to_send).strip()
        logger.info("feishu.outbound session_id={} content={}", session_id, content[:200])
        source = self._latest_message_by_session.get(session_id)
        if source is None:
            logger.warning("feishu.outbound unresolved source session_id={}", session_id)
            return

        for chunk in self._chunk_text(content):
            await asyncio.to_thread(self._send_text_sync, source, chunk)

    def _run_ws_client(self) -> None:
        if self._ws_client is None:
            return

        ws_module: Any = importlib.import_module("lark_oapi.ws.client")
        loop = asyncio.new_event_loop()
        self._ws_loop = loop
        ws_module.loop = loop
        asyncio.set_event_loop(loop)
        self._ws_started.set()

        try:
            self._ws_client.start()
        except RuntimeError:
            if not self._ws_stop_requested.is_set():
                logger.exception("feishu.ws.runtime_error")
        except Exception:
            if not self._ws_stop_requested.is_set():
                logger.exception("feishu.ws.error")
        finally:
            with contextlib.suppress(Exception):
                loop.close()
            self._ws_loop = None

    async def _shutdown_ws(self) -> None:
        self._ws_stop_requested.set()
        loop = self._ws_loop
        ws_client = self._ws_client

        if loop and loop.is_running() and ws_client is not None:
            with contextlib.suppress(Exception):
                fut = asyncio.run_coroutine_threadsafe(ws_client._disconnect(), loop)
                fut.result(timeout=3)
            with contextlib.suppress(Exception):
                loop.call_soon_threadsafe(loop.stop)

        if self._ws_thread is not None:
            await asyncio.to_thread(self._ws_thread.join, 3)
            if self._ws_thread.is_alive():
                logger.warning("feishu.ws.join_timeout")
            self._ws_thread = None

        self._ws_client = None

    def _on_message_event(self, data: Any) -> None:
        message = self._normalize_inbound(data)
        if message is None:
            return
        if not self._is_allowed(message):
            logger.warning(
                "feishu.inbound.denied chat_id={} sender_open_id={} reason=allowlist",
                message.chat_id,
                message.sender_open_id,
            )
            return
        if self._on_receive is None or self._main_loop is None:
            logger.warning("feishu.inbound no handler for received messages")
            return
        logger.info(
            "feishu.inbound chat_id={} sender_open_id={} message_id={} content={}",
            message.chat_id,
            message.sender_open_id,
            message.message_id,
            message.text[:100],
        )
        future: Any = asyncio.run_coroutine_threadsafe(self._dispatch_inbound(message), self._main_loop)
        future.add_done_callback(self._log_callback_exception)

    async def _dispatch_inbound(self, message: FeishuMessage) -> None:
        if self._on_receive is None:
            return
        await self._on_receive(message)

    @staticmethod
    def _log_callback_exception(future: Any) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            exc = future.exception()
            if exc is not None:
                logger.exception("feishu.inbound.callback.error: {}", exc)

    def _normalize_inbound(self, data: Any) -> FeishuMessage | None:
        payload = self._to_payload_dict(data)
        event = payload.get("event")
        if not isinstance(event, dict):
            return None
        message = event.get("message")
        sender = event.get("sender")
        if not isinstance(message, dict) or not isinstance(sender, dict):
            return None

        sender_id = sender.get("sender_id")
        sender_id_obj = sender_id if isinstance(sender_id, dict) else {}
        mentions: list[FeishuMention] = []
        raw_mentions = message.get("mentions")
        if isinstance(raw_mentions, list):
            for raw in raw_mentions:
                if not isinstance(raw, dict):
                    continue
                mention_id = raw.get("id")
                mention_id_obj = mention_id if isinstance(mention_id, dict) else {}
                mentions.append(
                    FeishuMention(
                        open_id=mention_id_obj.get("open_id"),
                        name=raw.get("name"),
                        key=raw.get("key"),
                    )
                )

        message_type = str(message.get("message_type") or "unknown")
        raw_content = str(message.get("content") or "")
        normalized = FeishuMessage(
            message_id=str(message.get("message_id") or ""),
            chat_id=str(message.get("chat_id") or ""),
            chat_type=str(message.get("chat_type") or ""),
            message_type=message_type,
            raw_content=raw_content,
            text=_normalize_text(message_type, raw_content),
            mentions=tuple(mentions),
            parent_id=message.get("parent_id"),
            root_id=message.get("root_id"),
            sender_id=sender_id_obj.get("open_id") or sender_id_obj.get("union_id") or sender_id_obj.get("user_id"),
            sender_open_id=sender_id_obj.get("open_id"),
            sender_union_id=sender_id_obj.get("union_id"),
            sender_user_id=sender_id_obj.get("user_id"),
            sender_type=sender.get("sender_type"),
            tenant_key=sender.get("tenant_key"),
            create_time=str(message.get("create_time") or ""),
            event_type=(payload.get("header") or {}).get("event_type"),
            raw_event=payload,
        )
        if not normalized.chat_id or not normalized.message_id:
            return None
        return normalized

    @staticmethod
    def _to_payload_dict(data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            return data
        if lark is not None:
            with contextlib.suppress(Exception):
                raw = lark.JSON.marshal(data)
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
        value = getattr(data, "__dict__", None)
        if isinstance(value, dict):
            return value
        return {}

    def _is_allowed(self, message: FeishuMessage) -> bool:
        if self._config.allow_chats and message.chat_id not in self._config.allow_chats:
            return False
        sender_tokens = {
            token
            for token in (
                message.sender_id,
                message.sender_open_id,
                message.sender_union_id,
                message.sender_user_id,
            )
            if token
        }
        return not (self._config.allow_from and sender_tokens.isdisjoint(self._config.allow_from))

    def _send_text_sync(self, source: FeishuMessage, text: str) -> None:
        if self._api_client is None:
            return

        content = json.dumps({"text": text}, ensure_ascii=False)
        response = None
        if source.message_id:
            reply_request: ReplyMessageRequest = (
                ReplyMessageRequest.builder()
                .message_id(source.message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("text")
                    .content(content)
                    .reply_in_thread(False)
                    .uuid(str(uuid.uuid4()))
                    .build()
                )
                .build()
            )
            response = self._api_client.im.v1.message.reply(reply_request)
            if response.success():
                self._record_bot_message_id(response)
                return
            logger.warning(
                "feishu.reply.failed code={} msg={} log_id={}",
                response.code,
                response.msg,
                response.get_log_id(),
            )

        create_request: CreateMessageRequest = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(source.chat_id)
                .msg_type("text")
                .content(content)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        response = self._api_client.im.v1.message.create(create_request)
        if response.success():
            self._record_bot_message_id(response)
            return
        logger.error(
            "feishu.create.failed code={} msg={} log_id={}",
            response.code,
            response.msg,
            response.get_log_id(),
        )

    def _record_bot_message_id(self, response: Any) -> None:
        with contextlib.suppress(Exception):
            message_id = getattr(response.data, "message_id", None)
            if message_id:
                self._bot_message_ids.add(str(message_id))

    @staticmethod
    def _chunk_text(text: str, *, limit: int = 4000) -> list[str]:
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
