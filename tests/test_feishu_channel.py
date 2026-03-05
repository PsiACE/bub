from __future__ import annotations

import json
from typing import Any

import pytest
from pytest import MonkeyPatch

from bub.core.agent_loop import LoopResult

feishu_module = pytest.importorskip("bub.channels.feishu")
FeishuChannel = feishu_module.FeishuChannel
FeishuMention = feishu_module.FeishuMention
FeishuMessage = feishu_module.FeishuMessage


def _build_channel() -> Any:
    from types import SimpleNamespace

    runtime = SimpleNamespace(
        settings=SimpleNamespace(
            feishu_app_id="cli_test",
            feishu_app_secret="secret",  # noqa: S106
            feishu_allow_from=[],
            feishu_allow_chats=[],
            proactive_response=False,
        )
    )
    return FeishuChannel(runtime)  # type: ignore[arg-type]


def _build_message(
    *,
    text: str,
    chat_type: str = "group",
    chat_id: str = "oc_chat_1",
    message_id: str = "om_1",
    mentions: tuple[Any, ...] = (),
) -> Any:
    return FeishuMessage(
        message_id=message_id,
        chat_id=chat_id,
        chat_type=chat_type,
        message_type="text",
        raw_content=json.dumps({"text": text}, ensure_ascii=False),
        text=text,
        mentions=mentions,
        parent_id=None,
        root_id=None,
        sender_id="ou_user_1",
        sender_open_id="ou_user_1",
        sender_union_id=None,
        sender_user_id=None,
        sender_type="user",
        tenant_key="tenant_1",
        create_time="123",
        event_type="im.message.receive_v1",
        raw_event={},
    )


@pytest.mark.asyncio
async def test_get_session_prompt_wraps_message_and_supports_comma_passthrough() -> None:
    channel = _build_channel()

    message = _build_message(text="hello from feishu", chat_type="group", chat_id="oc_group_42")
    session_id, prompt = await channel.get_session_prompt(message)  # type: ignore[arg-type]

    assert session_id == "feishu:oc_group_42"
    data = json.loads(prompt)
    assert data["message"] == "hello from feishu"
    assert data["chat_id"] == "oc_group_42"
    assert data["message_id"] == "om_1"

    command_message = _build_message(text=",status", chat_type="group", chat_id="oc_group_42")
    command_session_id, command_prompt = await channel.get_session_prompt(command_message)  # type: ignore[arg-type]

    assert command_session_id == "feishu:oc_group_42"
    assert command_prompt == ",status"


def test_is_mentioned_supports_p2p_and_group_cases() -> None:
    channel = _build_channel()

    p2p_message = _build_message(text="hello", chat_type="p2p")
    assert channel.is_mentioned(p2p_message) is True  # type: ignore[arg-type]

    group_message = _build_message(text="hello", chat_type="group")
    assert channel.is_mentioned(group_message) is False  # type: ignore[arg-type]

    mention = FeishuMention(open_id="ou_bot", name="Bub", key="@_user_1")
    group_mention_message = _build_message(text="ping", chat_type="group", mentions=(mention,))
    assert channel.is_mentioned(group_mention_message) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_process_output_includes_assistant_when_not_proactive(monkeypatch: MonkeyPatch) -> None:
    channel = _build_channel()
    source = _build_message(text="hello", chat_id="oc_group_42")
    channel._latest_message_by_session["feishu:oc_group_42"] = source  # type: ignore[attr-defined]

    sent_chunks: list[str] = []

    def _fake_send_text_sync(_source: Any, text: str) -> None:
        sent_chunks.append(text)

    monkeypatch.setattr(channel, "_send_text_sync", _fake_send_text_sync)

    output = LoopResult(
        immediate_output="immediate reply",
        assistant_output="assistant details",
        exit_requested=False,
        steps=1,
        error="boom",
    )
    await channel.process_output("feishu:oc_group_42", output)

    payload = "\n".join(sent_chunks)
    assert "immediate reply" in payload
    assert "assistant details" in payload
    assert "Error: boom" in payload


@pytest.mark.asyncio
async def test_process_output_skips_assistant_when_proactive(monkeypatch: MonkeyPatch) -> None:
    channel = _build_channel()
    channel.runtime.settings.proactive_response = True
    source = _build_message(text="hello", chat_id="oc_group_42")
    channel._latest_message_by_session["feishu:oc_group_42"] = source  # type: ignore[attr-defined]

    sent_chunks: list[str] = []

    def _fake_send_text_sync(_source: Any, text: str) -> None:
        sent_chunks.append(text)

    monkeypatch.setattr(channel, "_send_text_sync", _fake_send_text_sync)

    output = LoopResult(
        immediate_output="",
        assistant_output="assistant details",
        exit_requested=False,
        steps=1,
        error=None,
    )
    await channel.process_output("feishu:oc_group_42", output)

    assert sent_chunks == []
