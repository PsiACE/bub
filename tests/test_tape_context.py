from republic import TapeEntry

from bub.tape.context import default_tape_context


def test_default_tape_context_includes_tool_messages() -> None:
    context = default_tape_context()
    assert context.select is not None

    entries = [
        TapeEntry.message({"role": "user", "content": "create a file"}),
        TapeEntry.tool_call([
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "fs.write", "arguments": '{"path":"a.txt","content":"hi"}'},
            },
            {
                "id": "call-2",
                "type": "function",
                "function": {"name": "fs.read", "arguments": '{"path":"a.txt"}'},
            },
        ]),
        TapeEntry.tool_result(["ok", {"content": "hi"}]),
        TapeEntry.message({"role": "assistant", "content": "done"}),
    ]

    messages = context.select(entries, context)
    assert messages[0] == {"role": "user", "content": "create a file"}
    assert messages[1]["role"] == "assistant"
    assert messages[1]["tool_calls"][0]["id"] == "call-1"
    assert messages[2] == {"role": "tool", "content": "ok", "tool_call_id": "call-1", "name": "fs.write"}
    assert messages[3] == {
        "role": "tool",
        "content": '{"content": "hi"}',
        "tool_call_id": "call-2",
        "name": "fs.read",
    }
    assert messages[4] == {"role": "assistant", "content": "done"}


def test_default_tape_context_handles_result_without_calls() -> None:
    context = default_tape_context()
    assert context.select is not None

    entries = [TapeEntry.tool_result([{"status": "ok"}])]
    messages = context.select(entries, context)

    assert messages == []


def test_default_tape_context_splits_concatenated_tool_arguments() -> None:
    context = default_tape_context()
    assert context.select is not None

    entries = [
        TapeEntry.tool_call([
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": '{"cmd":"echo 1"}{"cmd":"echo 2"}',
                },
            }
        ]),
        TapeEntry.tool_result(["ok-1", "ok-2"]),
    ]

    messages = context.select(entries, context)
    assert messages[0]["role"] == "assistant"
    assert len(messages[0]["tool_calls"]) == 2
    assert messages[0]["tool_calls"][0]["function"]["arguments"] == '{"cmd":"echo 1"}'
    assert messages[0]["tool_calls"][1]["function"]["arguments"] == '{"cmd":"echo 2"}'
    assert messages[1]["tool_call_id"] == "call-1"
    assert messages[2]["tool_call_id"] == "call-1__2"


def test_default_tape_context_drops_invalid_tool_call_arguments() -> None:
    context = default_tape_context()
    assert context.select is not None

    entries = [
        TapeEntry.tool_call([
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": '{"cmd":"echo 1"}this-is-bad',
                },
            }
        ]),
        TapeEntry.tool_result(["ignored"]),
    ]

    messages = context.select(entries, context)
    assert messages == []


def test_default_tape_context_trims_unmatched_split_tool_calls() -> None:
    context = default_tape_context()
    assert context.select is not None

    entries = [
        TapeEntry.tool_call([
            {
                "id": "call-1",
                "type": "function",
                "function": {
                    "name": "bash",
                    "arguments": '{"cmd":"echo 1"}{"cmd":"echo 2"}',
                },
            }
        ]),
        TapeEntry.tool_result(["only-one-result"]),
    ]

    messages = context.select(entries, context)
    assert len(messages) == 2
    assert messages[0]["role"] == "assistant"
    assert len(messages[0]["tool_calls"]) == 1
    assert messages[0]["tool_calls"][0]["id"] == "call-1"
    assert messages[1]["role"] == "tool"
    assert messages[1]["tool_call_id"] == "call-1"
