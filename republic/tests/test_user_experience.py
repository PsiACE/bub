from __future__ import annotations

from types import SimpleNamespace

from republic import LLM, tool
from republic.core.errors import ErrorKind

from .fakes import make_chunk, make_response, make_tool_call


def test_chat_retries_and_returns_structured_output(fake_anyllm) -> None:
    client = fake_anyllm.ensure("openai")
    client.queue_completion(RuntimeError("temporary failure"), make_response(text="ready"))

    llm = LLM(
        model="openai:gpt-4o-mini",
        api_key="dummy",
        max_retries=2,
        error_classifier=lambda _: ErrorKind.TEMPORARY,
    )

    out = llm.chat("Reply with ready", max_tokens=8)

    assert out.error is None
    assert out.value == "ready"
    assert len(client.calls) == 2


def test_chat_uses_fallback_model(fake_anyllm) -> None:
    primary = fake_anyllm.ensure("openai")
    fallback = fake_anyllm.ensure("anthropic")

    primary.queue_completion(RuntimeError("primary down"))
    fallback.queue_completion(make_response(text="fallback ok"))

    llm = LLM(
        model="openai:gpt-4o-mini",
        fallback_models=["anthropic:claude-3-5-sonnet-latest"],
        max_retries=1,
        api_key={"openai": "x", "anthropic": "y"},
        error_classifier=lambda _: ErrorKind.TEMPORARY,
    )

    out = llm.chat("Ping")

    assert out.error is None
    assert out.value == "fallback ok"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


def test_chat_fallbacks_on_auth_error(fake_anyllm) -> None:
    class FakeAuthError(Exception):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.status_code = 401

    primary = fake_anyllm.ensure("openai")
    fallback = fake_anyllm.ensure("openrouter")

    primary.queue_completion(FakeAuthError("invalid api key"))
    fallback.queue_completion(make_response(text="fallback ok"))

    llm = LLM(
        model="openai:gpt-4o-mini",
        fallback_models=["openrouter:openrouter/free"],
        max_retries=2,
        api_key={"openai": "bad", "openrouter": "ok"},
    )

    out = llm.chat("Ping")

    assert out.error is None
    assert out.value == "fallback ok"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


def test_chat_fallbacks_on_rate_limit_like_error(fake_anyllm) -> None:
    class FakeRateLimitError(Exception):
        def __init__(self, message: str) -> None:
            super().__init__(message)
            self.status_code = 429

    primary = fake_anyllm.ensure("openai")
    fallback = fake_anyllm.ensure("openrouter")

    primary.queue_completion(FakeRateLimitError("too many requests"))
    fallback.queue_completion(make_response(text="fallback ok"))

    llm = LLM(
        model="openai:gpt-4o-mini",
        fallback_models=["openrouter:openrouter/free"],
        max_retries=1,
        api_key={"openai": "x", "openrouter": "y"},
    )

    out = llm.chat("Ping")

    assert out.error is None
    assert out.value == "fallback ok"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


def test_tape_requires_anchor_then_records_full_run(fake_anyllm) -> None:
    client = fake_anyllm.ensure("openai")
    client.queue_completion(make_response(text="step one"), make_response(text="step two"))

    llm = LLM(model="openai:gpt-4o-mini", api_key="dummy")
    tape = llm.tape("ops")

    missing_anchor = tape.chat("Investigate DB timeout")
    assert missing_anchor.error is not None
    assert missing_anchor.error.kind == ErrorKind.NOT_FOUND
    assert len(client.calls) == 0

    tape.handoff("incident_42", state={"owner": "tier1"})
    first = tape.chat("Investigate DB timeout")
    second = tape.chat("Include rollback criteria")

    assert first.error is None
    assert second.error is None

    second_messages = client.calls[-1]["messages"]
    assert [message["role"] for message in second_messages] == ["user", "assistant", "user"]

    entries = tape.read_entries()
    kinds = [entry.kind for entry in entries]
    assert kinds[0] == "error"
    assert entries[0].payload["kind"] == ErrorKind.NOT_FOUND.value
    assert "anchor" in kinds
    assert kinds[-1] == "event"

    run_event = entries[-1]
    assert run_event.payload["name"] == "run"
    assert run_event.payload["data"]["status"] == "ok"


@tool
def echo(text: str) -> str:
    return text.upper()


def test_stream_events_carries_text_tools_usage_and_final(fake_anyllm) -> None:
    client = fake_anyllm.ensure("openai")
    client.queue_completion(
        iter([
            make_chunk(text="Checking "),
            make_chunk(tool_calls=[make_tool_call("echo", '{"text":"to', call_id="call_1")]),
            make_chunk(
                tool_calls=[make_tool_call("echo", 'kyo"}', call_id="call_1")],
                usage={"total_tokens": 12},
            ),
        ])
    )

    llm = LLM(model="openai:gpt-4o-mini", api_key="dummy")
    stream = llm.stream_events("Call echo for tokyo", tools=[echo])
    events = list(stream)

    kinds = [event.kind for event in events]
    assert "text" in kinds
    assert "tool_call" in kinds
    assert "tool_result" in kinds
    assert "usage" in kinds
    assert kinds[-1] == "final"

    tool_result = next(event for event in events if event.kind == "tool_result")
    assert tool_result.data["result"] == "TOKYO"
    assert stream.error is None
    assert stream.usage == {"total_tokens": 12}


def test_stream_events_merges_tool_deltas_without_id_or_index(fake_anyllm) -> None:
    client = fake_anyllm.ensure("openai")
    client.queue_completion(
        iter([
            make_chunk(tool_calls=[make_tool_call("echo", '{"text":"to', call_id="call_1")]),
            make_chunk(
                tool_calls=[
                    SimpleNamespace(
                        type="function",
                        function=SimpleNamespace(name="", arguments='kyo"}'),
                    )
                ],
                usage={"total_tokens": 9},
            ),
        ])
    )

    llm = LLM(model="openai:gpt-4o-mini", api_key="dummy")
    stream = llm.stream_events("Call echo for tokyo", tools=[echo])
    events = list(stream)

    tool_calls = [event for event in events if event.kind == "tool_call"]
    assert len(tool_calls) == 1
    assert tool_calls[0].data["call"]["function"]["name"] == "echo"
    assert tool_calls[0].data["call"]["function"]["arguments"] == '{"text":"tokyo"}'

    tool_results = [event for event in events if event.kind == "tool_result"]
    assert len(tool_results) == 1
    assert tool_results[0].data["result"] == "TOKYO"
    assert stream.error is None
    assert stream.usage == {"total_tokens": 9}


def test_text_shortcuts_and_embeddings_share_the_same_facade(fake_anyllm) -> None:
    client = fake_anyllm.ensure("openai")
    client.queue_completion(
        make_response(tool_calls=[make_tool_call("if_decision", '{"value": true}')]),
        make_response(tool_calls=[make_tool_call("classify_decision", '{"label": "support"}')]),
        make_response(tool_calls=[make_tool_call("classify_decision", '{"label": "other"}')]),
    )
    client.queue_embedding({"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    llm = LLM(model="openai:gpt-4o-mini", api_key="dummy")

    decision = llm.if_("The service is down", "Should we page on-call?")
    assert decision.error is None
    assert decision.value is True

    label = llm.classify("Need invoice support", ["support", "sales"])
    assert label.error is None
    assert label.value == "support"

    invalid_label = llm.classify("Unknown intent", ["support", "sales"])
    assert invalid_label.error is not None
    assert invalid_label.error.kind == ErrorKind.INVALID_INPUT

    embedding = llm.embed("incident summary")
    assert embedding.error is None
    assert embedding.value == {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
