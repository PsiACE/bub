from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from bub.channels.telegram import BubMessageFilter


@dataclass
class DummyUser:
    id: int


@dataclass
class DummyEntity:
    type: str
    offset: int = 0
    length: int = 0
    user: DummyUser | None = None


class DummyMessage:
    def __init__(
        self,
        *,
        text: str,
        chat_type: str,
        bot_id: int = 1000,
        bot_username: str = "BubBot",
        entities: list[DummyEntity] | None = None,
        reply_to_message: object | None = None,
    ) -> None:
        self.text = text
        self.chat = SimpleNamespace(type=chat_type)
        self.entities = entities or []
        self.reply_to_message = reply_to_message
        self._bot_id = bot_id
        self._bot_username = bot_username

    def get_bot(self) -> object:
        return SimpleNamespace(id=self._bot_id, username=self._bot_username)


def test_group_allows_bot_prefix() -> None:
    message = DummyMessage(text="/bot hello", chat_type="group")
    assert BubMessageFilter().filter(message) is True


def test_group_allows_at_mention_by_username_entity() -> None:
    message = DummyMessage(
        text="@BubBot ping",
        chat_type="supergroup",
        entities=[DummyEntity(type="mention", offset=0, length=7)],
    )
    assert BubMessageFilter().filter(message) is True


def test_group_allows_at_mention_by_text_mention_entity() -> None:
    message = DummyMessage(
        text="ping bot",
        chat_type="group",
        entities=[DummyEntity(type="text_mention", user=DummyUser(id=1000))],
    )
    assert BubMessageFilter().filter(message) is True


def test_group_allows_reply_to_bot_message() -> None:
    reply_to_message = SimpleNamespace(from_user=SimpleNamespace(id=1000))
    message = DummyMessage(text="reply", chat_type="group", reply_to_message=reply_to_message)
    assert BubMessageFilter().filter(message) is True


def test_group_rejects_unrelated_text() -> None:
    message = DummyMessage(text="hello world", chat_type="group")
    assert BubMessageFilter().filter(message) is False
