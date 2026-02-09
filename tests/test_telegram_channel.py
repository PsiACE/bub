from __future__ import annotations

from types import SimpleNamespace

from bub.channels.telegram import TelegramChannel, TelegramConfig


def _channel() -> TelegramChannel:
    return TelegramChannel(  # type: ignore[arg-type]
        bus=SimpleNamespace(),
        config=TelegramConfig(token="t", allow_from=set()),  # noqa: S106
    )


def test_compose_inbound_text_appends_reply_context_for_plain_text() -> None:
    channel = _channel()

    reply_user = SimpleNamespace(username="alice", first_name="Alice", last_name="", id=100)
    reply_message = SimpleNamespace(text="hello from above", caption=None, from_user=reply_user)
    message = SimpleNamespace(reply_to_message=reply_message)

    composed = channel._compose_inbound_text(message, "new question")
    assert "new question" in composed
    assert "<reply_context>" in composed
    assert "from: @alice" in composed
    assert "quote: hello from above" in composed
    assert "partial: false" in composed
    assert "rule: if partial=true, recover from ctx by head/tail first; if uncertain ask full quote; no guess" in composed
    assert "if_miss: ask user to paste full quote" in composed


def test_compose_inbound_text_keeps_command_unchanged() -> None:
    channel = _channel()

    reply_user = SimpleNamespace(username="alice", first_name="Alice", last_name="", id=100)
    reply_message = SimpleNamespace(text="hello from above", caption=None, from_user=reply_user)
    message = SimpleNamespace(reply_to_message=reply_message)

    composed = channel._compose_inbound_text(message, ",tape.info")
    assert composed == ",tape.info"


def test_compose_inbound_text_truncates_long_reply_text() -> None:
    channel = _channel()

    long_text = "x" * (channel.REPLY_CONTEXT_MAX_CHARS + 10)
    reply_user = SimpleNamespace(username=None, first_name="Bob", last_name="Lee", id=200)
    reply_message = SimpleNamespace(text=long_text, caption=None, from_user=reply_user)
    message = SimpleNamespace(reply_to_message=reply_message)

    composed = channel._compose_inbound_text(message, "ask")
    assert "from: Bob Lee" in composed
    assert "partial: true" in composed
    assert "head:" in composed
    assert "tail:" in composed
    assert f"chars: {len(long_text)}" in composed


def test_compose_inbound_text_uses_caption_when_text_missing() -> None:
    channel = _channel()

    reply_user = SimpleNamespace(username="alice", first_name="Alice", last_name="", id=100)
    reply_message = SimpleNamespace(text=None, caption="image caption", from_user=reply_user)
    message = SimpleNamespace(reply_to_message=reply_message)

    composed = channel._compose_inbound_text(message, "check")
    assert "quote: image caption" in composed
    assert "partial: false" in composed
