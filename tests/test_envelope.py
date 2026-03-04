from dataclasses import dataclass

from bub.envelope import content_of, field_of, normalize_envelope, unpack_batch


@dataclass
class _Message:
    content: str
    channel: str = "cli"


def test_field_of_supports_mapping_and_object() -> None:
    mapping = {"content": "hello", "count": 3}
    assert field_of(mapping, "content") == "hello"
    assert field_of(mapping, "missing", "fallback") == "fallback"

    obj = _Message(content="world")
    assert field_of(obj, "content") == "world"
    assert field_of(obj, "missing", "fallback") == "fallback"


def test_content_of_stringifies_value() -> None:
    assert content_of({"content": 123}) == "123"
    assert content_of({"other": "x"}) == ""


def test_normalize_envelope_for_mapping_object_and_raw_value() -> None:
    mapping = {"content": "hello"}
    normalized_mapping = normalize_envelope(mapping)
    assert normalized_mapping == mapping
    assert normalized_mapping is not mapping

    obj = _Message(content="world", channel="telegram")
    assert normalize_envelope(obj) == {"content": "world", "channel": "telegram"}

    assert normalize_envelope(42) == {"content": "42"}


def test_unpack_batch_handles_none_sequence_and_single_item() -> None:
    assert unpack_batch(None) == []
    assert unpack_batch([{"content": "a"}]) == [{"content": "a"}]
    assert unpack_batch(({"content": "a"}, {"content": "b"})) == [{"content": "a"}, {"content": "b"}]
    assert unpack_batch({"content": "single"}) == [{"content": "single"}]
