"""Chat helpers for Republic."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from typing import Any

from republic.core.errors import ErrorKind, RepublicError
from republic.core.execution import LLMCore
from republic.core.results import (
    AsyncStreamEvents,
    AsyncTextStream,
    ErrorPayload,
    StreamEvent,
    StreamEvents,
    StreamState,
    StructuredOutput,
    TextStream,
    ToolAutoResult,
)
from republic.tape.context import ContextSelection, TapeContext, build_messages
from republic.tape.entries import TapeEntry
from republic.tape.query import TapeQuery
from republic.tape.store import InMemoryTapeStore, TapeStore
from republic.tools.context import ToolContext
from republic.tools.executor import ToolExecutor
from republic.tools.schema import ToolInput, ToolSet, normalize_tools

MessageInput = dict[str, Any]


@dataclass(frozen=True)
class PreparedChat:
    payload: list[dict[str, Any]]
    new_messages: list[dict[str, Any]]
    toolset: ToolSet
    tape: str | None
    should_update: bool
    context_error: ErrorPayload | None
    run_id: str
    system_prompt: str | None


class ToolCallAssembler:
    def __init__(self) -> None:
        self._calls: dict[object, dict[str, Any]] = {}
        self._order: list[object] = []
        self._index_to_key: dict[Any, object] = {}

    def _replace_key(self, old_key: object, new_key: object) -> None:
        entry = self._calls.pop(old_key)
        self._calls[new_key] = entry
        self._order[self._order.index(old_key)] = new_key
        for index, key in list(self._index_to_key.items()):
            if key == old_key:
                self._index_to_key[index] = new_key

    def _key_at_position(self, position: int) -> object | None:
        if position < len(self._order):
            return self._order[position]
        return None

    def _resolve_key_by_id(self, call_id: str, index: Any, position: int) -> object:
        id_key: object = ("id", call_id)
        if id_key in self._calls:
            if index is not None:
                self._index_to_key[index] = id_key
            return id_key

        mapped_key = self._index_to_key.get(index) if index is not None else None
        if mapped_key is not None and mapped_key in self._calls and mapped_key != id_key:
            self._replace_key(mapped_key, id_key)
            self._index_to_key[index] = id_key
            return id_key

        if index is not None:
            index_key: object = ("index", index)
            if index_key in self._calls:
                self._replace_key(index_key, id_key)
                self._index_to_key[index] = id_key
                return id_key

        position_key = self._key_at_position(position)
        if position_key is not None and position_key in self._calls:
            self._replace_key(position_key, id_key)
            if index is not None:
                self._index_to_key[index] = id_key
            return id_key
        if index is not None:
            self._index_to_key[index] = id_key
        return id_key

    def _resolve_key_by_index(self, tool_call: Any, index: Any, position: int) -> object:
        mapped_key = self._index_to_key.get(index)
        if mapped_key is not None and mapped_key in self._calls:
            return mapped_key

        index_key: object = ("index", index)
        if index_key in self._calls:
            self._index_to_key[index] = index_key
            return index_key

        position_key = self._key_at_position(position)
        func = getattr(tool_call, "function", None)
        tool_name = getattr(func, "name", None) if func is not None else None

        if (tool_name is None or tool_name == "") and position_key is not None and position_key in self._calls:
            self._index_to_key[index] = position_key
            return position_key

        if (
            position_key is not None
            and position_key in self._calls
            and isinstance(position_key, tuple)
            and position_key[0] == "position"
        ):
            self._replace_key(position_key, index_key)
            self._index_to_key[index] = index_key
            return index_key
        self._index_to_key[index] = index_key
        return index_key

    def _resolve_key(self, tool_call: Any, position: int) -> object:
        call_id = getattr(tool_call, "id", None)
        index = getattr(tool_call, "index", None)

        if call_id is not None:
            return self._resolve_key_by_id(call_id, index, position)

        if index is not None:
            return self._resolve_key_by_index(tool_call, index, position)

        # Some providers omit id/index for follow-up tool-call deltas.
        # Merge by positional order so argument fragments are not split into fake calls.
        position_key = self._key_at_position(position)
        if position_key is not None:
            return position_key
        return ("position", position)

    def add_deltas(self, tool_calls: list[Any]) -> None:
        for position, tool_call in enumerate(tool_calls):
            key = self._resolve_key(tool_call, position)
            if key not in self._calls:
                self._order.append(key)
                self._calls[key] = {"function": {"name": "", "arguments": ""}}
            entry = self._calls[key]
            call_id = getattr(tool_call, "id", None)
            if call_id:
                entry["id"] = call_id
            call_type = getattr(tool_call, "type", None)
            if call_type:
                entry["type"] = call_type
            func = getattr(tool_call, "function", None)
            if func is None:
                continue
            name = getattr(func, "name", None)
            if name:
                entry["function"]["name"] = name
            arguments = getattr(func, "arguments", None)
            if arguments:
                entry["function"]["arguments"] = entry["function"].get("arguments", "") + arguments

    def finalize(self) -> list[dict[str, Any]]:
        return [self._calls[key] for key in self._order]


class ChatClient:
    """Chat operations with structured outputs."""

    def __init__(
        self,
        core: LLMCore,
        tool_executor: ToolExecutor,
        store: TapeStore | None = None,
        context: TapeContext | None = None,
    ) -> None:
        self._core = core
        self._tool_executor = tool_executor
        self._tape_store = store or InMemoryTapeStore()
        self._default_context = context or TapeContext()

    @property
    def default_context(self) -> TapeContext:
        return self._default_context

    def _validate_chat_input(
        self,
        *,
        prompt: str | None,
        messages: list[MessageInput] | None,
        system_prompt: str | None,
        tape: str | None,
    ) -> ErrorPayload | None:
        if prompt is not None and messages is not None:
            return ErrorPayload(ErrorKind.INVALID_INPUT, "Provide either prompt or messages, not both.")
        if prompt is None and messages is None:
            return ErrorPayload(ErrorKind.INVALID_INPUT, "Either prompt or messages is required.")
        if messages is not None and (system_prompt is not None or tape is not None):
            return ErrorPayload(
                ErrorKind.INVALID_INPUT,
                "system_prompt and tape are not supported with messages input.",
            )
        return None

    def _prepare_messages(
        self,
        prompt: str | None,
        system_prompt: str | None,
        tape: str | None,
        messages: list[MessageInput] | None,
        context: TapeContext | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], ErrorPayload | None]:
        error = self._validate_chat_input(
            prompt=prompt,
            messages=messages,
            system_prompt=system_prompt,
            tape=tape,
        )
        if error is not None:
            return [], [], error

        if messages is not None:
            payload = [dict(message) for message in messages]
            return payload, [], None

        if prompt is None:
            return [], [], ErrorPayload(ErrorKind.INVALID_INPUT, "prompt is required when messages is not provided")

        user_message = {"role": "user", "content": prompt}

        if tape is None:
            payload: list[dict[str, Any]] = []
            if system_prompt:
                payload.append({"role": "system", "content": system_prompt})
            payload.append(user_message)
            return payload, [], None

        selection = self.read_messages(tape, context=context)
        history = selection.messages
        payload = []
        if system_prompt:
            payload.append({"role": "system", "content": system_prompt})
        payload.extend(history)
        payload.append(user_message)
        return payload, [user_message], selection.error

    def _prepare_request(
        self,
        *,
        prompt: str | None,
        system_prompt: str | None,
        messages: list[MessageInput] | None,
        tape: str | None,
        context: TapeContext | None,
        tools: ToolInput,
        require_tools: bool = False,
        require_runnable: bool = False,
    ) -> PreparedChat:
        if require_tools and not tools:
            tools_error = ErrorPayload(ErrorKind.INVALID_INPUT, "tools are required for this operation.")
        else:
            tools_error = None

        payload, new_messages, context_error = self._prepare_messages(
            prompt,
            system_prompt,
            tape,
            messages,
            context=context,
        )
        toolset, tool_error = self._normalize_tools(tools)
        if tools_error is not None and context_error is None:
            context_error = tools_error
        if tool_error is not None:
            context_error = tool_error if context_error is None else context_error
        if require_runnable:
            try:
                toolset.require_runnable()
            except ValueError as exc:
                context_error = ErrorPayload(ErrorKind.INVALID_INPUT, str(exc))

        should_update = tape is not None and messages is None
        run_id = uuid.uuid4().hex
        return PreparedChat(
            payload=payload,
            new_messages=new_messages,
            toolset=toolset,
            tape=tape,
            should_update=should_update,
            context_error=context_error,
            run_id=run_id,
            system_prompt=system_prompt,
        )

    def _execute_sync(
        self,
        prepared: PreparedChat,
        *,
        tools_payload: list[dict[str, Any]] | None,
        model: str | None,
        provider: str | None,
        max_tokens: int | None,
        stream: bool,
        tool_count: int,
        kwargs: dict[str, Any],
        on_response: Callable[[Any, str, str, int], Any],
        on_error: Callable[[ErrorPayload], Any],
    ) -> Any:
        if prepared.context_error is not None:
            return on_error(prepared.context_error)
        try:
            return self._core.run_chat_sync(
                messages_payload=prepared.payload,
                tools_payload=tools_payload,
                model=model,
                provider=provider,
                max_tokens=max_tokens,
                stream=stream,
                reasoning_effort=None,
                tool_count=tool_count,
                kwargs=kwargs,
                on_response=on_response,
            )
        except RepublicError as exc:
            return on_error(ErrorPayload(exc.kind, exc.message))

    async def _execute_async(
        self,
        prepared: PreparedChat,
        *,
        tools_payload: list[dict[str, Any]] | None,
        model: str | None,
        provider: str | None,
        max_tokens: int | None,
        stream: bool,
        tool_count: int,
        kwargs: dict[str, Any],
        on_response: Callable[[Any, str, str, int], Any],
        on_error: Callable[[ErrorPayload], Any],
    ) -> Any:
        if prepared.context_error is not None:
            return on_error(prepared.context_error)
        try:
            return await self._core.run_chat_async(
                messages_payload=prepared.payload,
                tools_payload=tools_payload,
                model=model,
                provider=provider,
                max_tokens=max_tokens,
                stream=stream,
                reasoning_effort=None,
                tool_count=tool_count,
                kwargs=kwargs,
                on_response=on_response,
            )
        except RepublicError as exc:
            return on_error(ErrorPayload(exc.kind, exc.message))

    def _normalize_tools(self, tools: ToolInput) -> tuple[ToolSet, ErrorPayload | None]:
        try:
            return normalize_tools(tools), None
        except (ValueError, TypeError) as exc:
            return ToolSet([], []), ErrorPayload(ErrorKind.INVALID_INPUT, str(exc))

    def read_entries(self, tape: str) -> list[TapeEntry]:
        return self._tape_store.read(tape) or []

    def read_messages(self, tape: str, *, context: TapeContext | None = None) -> ContextSelection:
        entries = self.read_entries(tape)
        active_context = context or self._default_context
        return build_messages(entries, active_context)

    def append_entry(self, tape: str, entry: TapeEntry) -> None:
        self._tape_store.append(tape, entry)

    def reset_tape(self, tape: str) -> None:
        self._tape_store.reset(tape)

    def query_tape(self, tape: str) -> TapeQuery:
        return TapeQuery(tape=tape, store=self._tape_store)

    def handoff(self, tape: str, name: str, *, state: dict[str, Any] | None = None, **meta: Any) -> list[TapeEntry]:
        entry = TapeEntry.anchor(name, state=state, **meta)
        event = TapeEntry.event("handoff", {"name": name, "state": state or {}}, **meta)
        self._tape_store.append(tape, entry)
        self._tape_store.append(tape, event)
        return [entry, event]

    def _append_tape_messages(self, tape: str, messages: list[dict[str, Any]], *, meta: dict[str, Any]) -> None:
        for message in messages:
            self._tape_store.append(tape, TapeEntry.message(message, **meta))

    def _append_tool_events(
        self,
        tape: str,
        tool_calls: list[dict[str, Any]] | None,
        tool_results: list[Any] | None,
        *,
        meta: dict[str, Any],
    ) -> None:
        if tool_calls:
            self._tape_store.append(tape, TapeEntry.tool_call(tool_calls, **meta))
        if tool_results is not None:
            self._tape_store.append(tape, TapeEntry.tool_result(tool_results, **meta))

    def _append_system_prompt(self, tape: str, system_prompt: str | None, *, meta: dict[str, Any]) -> None:
        if system_prompt:
            self._tape_store.append(tape, TapeEntry.system(system_prompt, **meta))

    def _append_error(self, tape: str, error: ErrorPayload, *, meta: dict[str, Any]) -> None:
        self._tape_store.append(tape, TapeEntry.error(error, **meta))

    def _append_run_event(
        self,
        tape: str,
        *,
        meta: dict[str, Any],
        status: str,
        response: Any | None,
        provider: str | None,
        model: str | None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        data: dict[str, Any] = {"status": status}
        resolved_usage = usage or self._extract_usage(response)
        if resolved_usage is not None:
            data["usage"] = resolved_usage
        if provider:
            data["provider"] = provider
        if model:
            data["model"] = model
        self._tape_store.append(tape, TapeEntry.event("run", data, **meta))

    def _update_tape(
        self,
        prepared: PreparedChat,
        response_text: str | None,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_results: list[Any] | None = None,
        error: ErrorPayload | None = None,
        response: Any | None = None,
        provider: str | None = None,
        model: str | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        if prepared.tape is None:
            return
        meta = {"run_id": prepared.run_id}
        self._append_system_prompt(prepared.tape, prepared.system_prompt, meta=meta)
        if prepared.context_error is not None:
            self._append_error(prepared.tape, prepared.context_error, meta=meta)
        self._append_tape_messages(prepared.tape, prepared.new_messages, meta=meta)
        self._append_tool_events(prepared.tape, tool_calls, tool_results, meta=meta)
        if error is not None:
            self._append_error(prepared.tape, error, meta=meta)
        if response_text is not None:
            self._tape_store.append(
                prepared.tape,
                TapeEntry.message({"role": "assistant", "content": response_text}, **meta),
            )
        self._append_run_event(
            prepared.tape,
            meta=meta,
            status="error" if error is not None else "ok",
            response=response,
            provider=provider,
            model=model,
            usage=usage,
        )

    @staticmethod
    def _empty_iterator() -> Iterator[str]:
        return iter(())

    @staticmethod
    async def _empty_async_iterator() -> AsyncIterator[str]:
        if False:
            yield ""

    def _structured_error_result(self, prepared: PreparedChat, error: ErrorPayload) -> StructuredOutput:
        if prepared.should_update:
            self._update_tape(prepared, None, error=error)
        return StructuredOutput(None, error)

    def _tool_auto_error_result(self, prepared: PreparedChat, error: ErrorPayload) -> ToolAutoResult:
        if prepared.should_update:
            self._update_tape(prepared, None, error=error)
        return ToolAutoResult.error_result(error)

    def _stream_error_result(self, prepared: PreparedChat, error: ErrorPayload) -> TextStream:
        if prepared.should_update:
            self._update_tape(prepared, None, error=error)
        return TextStream(self._empty_iterator(), state=StreamState(error=error))

    def _stream_async_error_result(self, prepared: PreparedChat, error: ErrorPayload) -> AsyncTextStream:
        if prepared.should_update:
            self._update_tape(prepared, None, error=error)
        return AsyncTextStream(self._empty_async_iterator(), state=StreamState(error=error))

    def _event_error_result(self, prepared: PreparedChat, error: ErrorPayload) -> StreamEvents:
        if prepared.should_update:
            self._update_tape(prepared, None, error=error)
        state = StreamState(error=error)
        events = [
            StreamEvent("error", error.as_dict()),
            StreamEvent(
                "final",
                self._final_event_data(
                    text=None,
                    tool_calls=[],
                    tool_results=[],
                    usage=None,
                    error=error,
                ),
            ),
        ]
        return StreamEvents(iter(events), state=state)

    def _event_async_error_result(self, prepared: PreparedChat, error: ErrorPayload) -> AsyncStreamEvents:
        if prepared.should_update:
            self._update_tape(prepared, None, error=error)
        state = StreamState(error=error)

        async def _iterator() -> AsyncIterator[StreamEvent]:
            yield StreamEvent("error", error.as_dict())
            yield StreamEvent(
                "final",
                self._final_event_data(
                    text=None,
                    tool_calls=[],
                    tool_results=[],
                    usage=None,
                    error=error,
                ),
            )

        return AsyncStreamEvents(_iterator(), state=state)

    @staticmethod
    def _final_event_data(
        *,
        text: str | None,
        tool_calls: list[dict[str, Any]],
        tool_results: list[Any],
        usage: dict[str, Any] | None,
        error: ErrorPayload | None,
    ) -> dict[str, Any]:
        return {
            "text": text,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "usage": usage,
            "ok": error is None,
        }

    def _finalize_text_stream(
        self,
        prepared: PreparedChat,
        *,
        text: str | None,
        tool_calls: list[dict[str, Any]],
        state: StreamState,
        provider_name: str,
        model_id: str,
        attempt: int,
        usage: dict[str, Any] | None = None,
        response: Any | None = None,
        log_empty: bool = False,
    ) -> None:
        if not text and not tool_calls and state.error is None:
            empty_error = RepublicError(ErrorKind.TEMPORARY, f"{provider_name}:{model_id}: empty response")
            if log_empty:
                self._core.log_error(empty_error, provider_name, model_id, attempt)
            state.error = ErrorPayload(empty_error.kind, empty_error.message)
        state.usage = usage
        if prepared.should_update:
            self._update_tape(
                prepared,
                text or None,
                tool_calls=tool_calls or None,
                tool_results=None,
                error=state.error,
                response=response,
                provider=provider_name,
                model=model_id,
                usage=usage,
            )

    def _finalize_event_stream(
        self,
        prepared: PreparedChat,
        *,
        parts: list[str],
        tool_calls: list[dict[str, Any]],
        state: StreamState,
        provider_name: str,
        model_id: str,
        attempt: int,
        usage: dict[str, Any] | None,
    ) -> tuple[list[StreamEvent], list[Any]]:
        events: list[StreamEvent] = []
        for idx, call in enumerate(tool_calls):
            events.append(StreamEvent("tool_call", {"index": idx, "call": call}))

        tool_results, tool_error = self._execute_tool_calls(
            prepared,
            tool_calls,
            provider_name,
            model_id,
        )
        if tool_results:
            for idx, result in enumerate(tool_results):
                events.append(StreamEvent("tool_result", {"index": idx, "result": result}))
        if tool_error is not None:
            state.error = tool_error
            events.append(StreamEvent("error", tool_error.as_dict()))

        if not parts and not tool_calls and state.error is None:
            empty = RepublicError(ErrorKind.TEMPORARY, f"{provider_name}:{model_id}: empty response")
            self._core.log_error(empty, provider_name, model_id, attempt)
            empty_error = ErrorPayload(empty.kind, empty.message)
            state.error = empty_error
            events.append(StreamEvent("error", empty_error.as_dict()))

        if usage is not None:
            events.append(StreamEvent("usage", usage))

        events.append(
            StreamEvent(
                "final",
                self._final_event_data(
                    text="".join(parts) if parts else None,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    usage=usage,
                    error=state.error,
                ),
            )
        )
        return events, tool_results

    def _finalize_event_stream_state(
        self,
        prepared: PreparedChat,
        *,
        parts: list[str],
        tool_calls: list[dict[str, Any]] | None,
        tool_results: list[Any],
        state: StreamState,
        provider_name: str,
        model_id: str,
        usage: dict[str, Any] | None,
        assembler: ToolCallAssembler,
    ) -> list[dict[str, Any]]:
        state.usage = usage
        final_calls = tool_calls or assembler.finalize()
        if prepared.should_update:
            self._update_tape(
                prepared,
                "".join(parts) if parts else None,
                tool_calls=final_calls or None,
                tool_results=tool_results or None,
                error=state.error,
                provider=provider_name,
                model=model_id,
                usage=usage,
            )
        return final_calls

    def _error_event_sequence(
        self,
        *,
        parts: list[str],
        tool_calls: list[dict[str, Any]],
        tool_results: list[Any],
        usage: dict[str, Any] | None,
        error: ErrorPayload,
    ) -> list[StreamEvent]:
        return [
            StreamEvent("error", error.as_dict()),
            StreamEvent(
                "final",
                self._final_event_data(
                    text="".join(parts) if parts else None,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    usage=usage,
                    error=error,
                ),
            ),
        ]

    def _handle_create_response(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
        attempt: int,
    ) -> StructuredOutput | object:
        text = self._extract_text(response)
        if text:
            if prepared.should_update:
                self._update_tape(
                    prepared,
                    text,
                    response=response,
                    provider=provider_name,
                    model=model_id,
                )
            return StructuredOutput(text, None)
        empty_error = RepublicError(ErrorKind.TEMPORARY, f"{provider_name}:{model_id}: empty response")
        self._core.log_error(empty_error, provider_name, model_id, attempt)
        return self._core.RETRY

    def _handle_tool_calls_response(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
        attempt: int,
    ) -> StructuredOutput:
        calls = self._extract_tool_calls(response)
        if prepared.should_update:
            self._update_tape(
                prepared,
                None,
                tool_calls=calls,
                tool_results=[],
                response=response,
                provider=provider_name,
                model=model_id,
            )
        return StructuredOutput(calls, None)

    def _handle_tools_auto_response(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
        attempt: int,
    ) -> ToolAutoResult | object:
        tool_calls = self._extract_tool_calls(response)
        if tool_calls:
            tool_context = ToolContext(
                tape=prepared.tape,
                run_id=prepared.run_id,
                meta={"provider": provider_name, "model": model_id},
                state={},
            )
            execution = self._tool_executor.execute(
                tool_calls,
                tools=prepared.toolset.runnable,
                context=tool_context,
            )
            if prepared.should_update:
                if execution.error is not None:
                    self._update_tape(
                        prepared,
                        None,
                        tool_calls=execution.tool_calls,
                        tool_results=execution.tool_results,
                        error=execution.error,
                        response=response,
                        provider=provider_name,
                        model=model_id,
                    )
                else:
                    self._update_tape(
                        prepared,
                        None,
                        tool_calls=execution.tool_calls,
                        tool_results=execution.tool_results,
                        response=response,
                        provider=provider_name,
                        model=model_id,
                    )
            if execution.error is not None:
                return ToolAutoResult.error_result(
                    execution.error,
                    tool_calls=execution.tool_calls,
                    tool_results=execution.tool_results,
                )
            return ToolAutoResult.tools_result(execution.tool_calls, execution.tool_results)

        text = self._extract_text(response)
        if text:
            if prepared.should_update:
                self._update_tape(
                    prepared,
                    text,
                    response=response,
                    provider=provider_name,
                    model=model_id,
                )
            return ToolAutoResult.text_result(text)

        empty_error = RepublicError(ErrorKind.TEMPORARY, f"{provider_name}:{model_id}: empty response")
        self._core.log_error(empty_error, provider_name, model_id, attempt)
        return self._core.RETRY

    def chat(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=None,
        )
        return self._execute_sync(
            prepared,
            tools_payload=None,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=False,
            tool_count=0,
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._handle_create_response(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._structured_error_result(prepared, error),
        )

    def tool_calls(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        tools: ToolInput = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=tools,
            require_tools=True,
        )
        return self._execute_sync(
            prepared,
            tools_payload=prepared.toolset.payload,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=False,
            tool_count=len(prepared.toolset.payload or []),
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._handle_tool_calls_response(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._structured_error_result(prepared, error),
        )

    def run_tools(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        tools: ToolInput = None,
        **kwargs: Any,
    ) -> ToolAutoResult:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=tools,
            require_tools=True,
            require_runnable=True,
        )
        return self._execute_sync(
            prepared,
            tools_payload=prepared.toolset.payload,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=False,
            tool_count=len(prepared.toolset.payload or []),
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._handle_tools_auto_response(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._tool_auto_error_result(prepared, error),
        )

    async def chat_async(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=None,
        )
        return await self._execute_async(
            prepared,
            tools_payload=None,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=False,
            tool_count=0,
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._handle_create_response(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._structured_error_result(prepared, error),
        )

    async def tool_calls_async(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        tools: ToolInput = None,
        **kwargs: Any,
    ) -> StructuredOutput:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=tools,
            require_tools=True,
        )
        return await self._execute_async(
            prepared,
            tools_payload=prepared.toolset.payload,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=False,
            tool_count=len(prepared.toolset.payload or []),
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._handle_tool_calls_response(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._structured_error_result(prepared, error),
        )

    async def run_tools_async(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        tools: ToolInput = None,
        **kwargs: Any,
    ) -> ToolAutoResult:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=tools,
            require_tools=True,
            require_runnable=True,
        )
        return await self._execute_async(
            prepared,
            tools_payload=prepared.toolset.payload,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=False,
            tool_count=len(prepared.toolset.payload or []),
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._handle_tools_auto_response(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._tool_auto_error_result(prepared, error),
        )

    def stream(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        **kwargs: Any,
    ) -> TextStream:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=None,
        )
        return self._execute_sync(
            prepared,
            tools_payload=None,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=True,
            tool_count=0,
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._build_text_stream(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._stream_error_result(prepared, error),
        )

    async def stream_async(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        **kwargs: Any,
    ) -> AsyncTextStream:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=None,
        )
        return await self._execute_async(
            prepared,
            tools_payload=None,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=True,
            tool_count=0,
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._build_async_text_stream(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._stream_async_error_result(prepared, error),
        )

    def stream_events(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        tools: ToolInput = None,
        **kwargs: Any,
    ) -> StreamEvents:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=tools,
        )
        return self._execute_sync(
            prepared,
            tools_payload=prepared.toolset.payload or None,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=True,
            tool_count=len(prepared.toolset.payload or []),
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._build_event_stream(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._event_error_result(prepared, error),
        )

    async def stream_events_async(
        self,
        prompt: str | None = None,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        messages: list[MessageInput] | None = None,
        max_tokens: int | None = None,
        tape: str | None = None,
        context: TapeContext | None = None,
        tools: ToolInput = None,
        **kwargs: Any,
    ) -> AsyncStreamEvents:
        prepared = self._prepare_request(
            prompt=prompt,
            system_prompt=system_prompt,
            messages=messages,
            tape=tape,
            context=context,
            tools=tools,
        )
        return await self._execute_async(
            prepared,
            tools_payload=prepared.toolset.payload or None,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            stream=True,
            tool_count=len(prepared.toolset.payload or []),
            kwargs=kwargs,
            on_response=lambda response, provider_name, model_id, attempt: self._build_async_event_stream(
                prepared,
                response,
                provider_name,
                model_id,
                attempt,
            ),
            on_error=lambda error: self._event_async_error_result(prepared, error),
        )

    def _build_text_stream(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
        attempt: int,
    ) -> TextStream:
        if hasattr(response, "choices"):
            text = self._extract_text(response)
            tool_calls = self._extract_tool_calls(response)
            state = StreamState()
            self._finalize_text_stream(
                prepared,
                text=text or None,
                tool_calls=tool_calls,
                state=state,
                provider_name=provider_name,
                model_id=model_id,
                attempt=attempt,
                usage=self._extract_usage(response),
                response=response,
                log_empty=False,
            )
            return TextStream(iter([text]) if text else self._empty_iterator(), state=state)

        state = StreamState()
        parts: list[str] = []
        assembler = ToolCallAssembler()

        usage: dict[str, Any] | None = None

        def _iterator() -> Iterator[str]:
            nonlocal usage
            try:
                for chunk in response:
                    deltas = self._extract_chunk_tool_call_deltas(chunk)
                    if deltas:
                        assembler.add_deltas(deltas)
                    text = self._extract_chunk_text(chunk)
                    if text:
                        parts.append(text)
                        yield text
                    usage = self._extract_usage(chunk) or usage
            except Exception as exc:
                kind = self._core.classify_exception(exc)
                wrapped = self._core.wrap_error(exc, kind, provider_name, model_id)
                state.error = ErrorPayload(wrapped.kind, wrapped.message)
            finally:
                tool_calls = assembler.finalize()
                self._finalize_text_stream(
                    prepared,
                    text="".join(parts) if parts else None,
                    tool_calls=tool_calls,
                    state=state,
                    provider_name=provider_name,
                    model_id=model_id,
                    attempt=attempt,
                    usage=usage,
                    log_empty=True,
                )

        return TextStream(_iterator(), state=state)

    def _build_async_text_stream(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
        attempt: int,
    ) -> AsyncTextStream:
        if hasattr(response, "choices"):
            text = self._extract_text(response)
            tool_calls = self._extract_tool_calls(response)
            state = StreamState()
            self._finalize_text_stream(
                prepared,
                text=text or None,
                tool_calls=tool_calls,
                state=state,
                provider_name=provider_name,
                model_id=model_id,
                attempt=attempt,
                usage=self._extract_usage(response),
                response=response,
                log_empty=False,
            )

            async def _single() -> AsyncIterator[str]:
                if text:
                    yield text

            return AsyncTextStream(_single(), state=state)

        state = StreamState()
        parts: list[str] = []
        usage: dict[str, Any] | None = None
        assembler = ToolCallAssembler()

        async def _iterator() -> AsyncIterator[str]:
            nonlocal usage
            try:
                async for chunk in response:
                    deltas = self._extract_chunk_tool_call_deltas(chunk)
                    if deltas:
                        assembler.add_deltas(deltas)
                    text = self._extract_chunk_text(chunk)
                    if text:
                        parts.append(text)
                        yield text
                    usage = self._extract_usage(chunk) or usage
            except Exception as exc:
                kind = self._core.classify_exception(exc)
                wrapped = self._core.wrap_error(exc, kind, provider_name, model_id)
                state.error = ErrorPayload(wrapped.kind, wrapped.message)
            finally:
                tool_calls = assembler.finalize()
                self._finalize_text_stream(
                    prepared,
                    text="".join(parts) if parts else None,
                    tool_calls=tool_calls,
                    state=state,
                    provider_name=provider_name,
                    model_id=model_id,
                    attempt=attempt,
                    usage=usage,
                    log_empty=True,
                )

        return AsyncTextStream(_iterator(), state=state)

    @staticmethod
    def _chunk_has_tool_calls(chunk: Any) -> bool:
        return bool(ChatClient._extract_chunk_tool_call_deltas(chunk))

    @staticmethod
    def _extract_chunk_tool_call_deltas(chunk: Any) -> list[Any]:
        choices = getattr(chunk, "choices", None)
        if not choices:
            return []
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            return []
        return getattr(delta, "tool_calls", None) or []

    @staticmethod
    def _extract_chunk_text(chunk: Any) -> str:
        choices = getattr(chunk, "choices", None)
        if not choices:
            return ""
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            return ""
        return getattr(delta, "content", "") or ""

    def _build_event_stream(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
        attempt: int,
    ) -> StreamEvents:
        if hasattr(response, "choices"):
            return self._build_event_stream_from_response(
                prepared,
                response,
                provider_name,
                model_id,
            )

        state = StreamState()
        usage: dict[str, Any] | None = None
        parts: list[str] = []
        tool_calls: list[dict[str, Any]] | None = None
        tool_results: list[Any] = []
        assembler = ToolCallAssembler()

        def _iterator() -> Iterator[StreamEvent]:
            nonlocal usage, tool_calls, tool_results
            try:
                for chunk in response:
                    usage = self._extract_usage(chunk) or usage
                    assembler.add_deltas(self._extract_chunk_tool_call_deltas(chunk))
                    text = self._extract_chunk_text(chunk)
                    if text:
                        parts.append(text)
                        yield StreamEvent("text", {"delta": text})

                tool_calls = assembler.finalize()
                events, tool_results = self._finalize_event_stream(
                    prepared,
                    parts=parts,
                    tool_calls=tool_calls,
                    state=state,
                    provider_name=provider_name,
                    model_id=model_id,
                    attempt=attempt,
                    usage=usage,
                )
                yield from events
            except Exception as exc:
                kind = self._core.classify_exception(exc)
                wrapped = self._core.wrap_error(exc, kind, provider_name, model_id)
                state.error = ErrorPayload(wrapped.kind, wrapped.message)
                final_calls = tool_calls or assembler.finalize()
                yield from self._error_event_sequence(
                    parts=parts,
                    tool_calls=final_calls,
                    tool_results=tool_results,
                    usage=usage,
                    error=state.error,
                )
            finally:
                tool_calls = self._finalize_event_stream_state(
                    prepared,
                    parts=parts,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    state=state,
                    provider_name=provider_name,
                    model_id=model_id,
                    usage=usage,
                    assembler=assembler,
                )

        return StreamEvents(_iterator(), state=state)

    def _build_async_event_stream(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
        attempt: int,
    ) -> AsyncStreamEvents:
        if hasattr(response, "choices"):
            return self._build_async_event_stream_from_response(
                prepared,
                response,
                provider_name,
                model_id,
            )

        state = StreamState()
        usage: dict[str, Any] | None = None
        parts: list[str] = []
        tool_calls: list[dict[str, Any]] | None = None
        tool_results: list[Any] = []
        assembler = ToolCallAssembler()

        async def _iterator() -> AsyncIterator[StreamEvent]:
            nonlocal usage, tool_calls, tool_results
            try:
                async for chunk in response:
                    usage = self._extract_usage(chunk) or usage
                    assembler.add_deltas(self._extract_chunk_tool_call_deltas(chunk))
                    text = self._extract_chunk_text(chunk)
                    if text:
                        parts.append(text)
                        yield StreamEvent("text", {"delta": text})

                tool_calls = assembler.finalize()
                events, tool_results = self._finalize_event_stream(
                    prepared,
                    parts=parts,
                    tool_calls=tool_calls,
                    state=state,
                    provider_name=provider_name,
                    model_id=model_id,
                    attempt=attempt,
                    usage=usage,
                )
                for event in events:
                    yield event
            except Exception as exc:
                kind = self._core.classify_exception(exc)
                wrapped = self._core.wrap_error(exc, kind, provider_name, model_id)
                state.error = ErrorPayload(wrapped.kind, wrapped.message)
                final_calls = tool_calls or assembler.finalize()
                for event in self._error_event_sequence(
                    parts=parts,
                    tool_calls=final_calls,
                    tool_results=tool_results,
                    usage=usage,
                    error=state.error,
                ):
                    yield event
            finally:
                tool_calls = self._finalize_event_stream_state(
                    prepared,
                    parts=parts,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    state=state,
                    provider_name=provider_name,
                    model_id=model_id,
                    usage=usage,
                    assembler=assembler,
                )

        return AsyncStreamEvents(_iterator(), state=state)

    def _build_event_stream_from_response(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
    ) -> StreamEvents:
        text = self._extract_text(response)
        tool_calls = self._extract_tool_calls(response)
        usage = self._extract_usage(response)
        tool_results, tool_error = self._execute_tool_calls(prepared, tool_calls, provider_name, model_id)
        if not text and not tool_calls and tool_error is None:
            empty = RepublicError(ErrorKind.TEMPORARY, f"{provider_name}:{model_id}: empty response")
            self._core.log_error(empty, provider_name, model_id, 0)
            tool_error = ErrorPayload(empty.kind, empty.message)
        state = StreamState(error=tool_error, usage=usage)
        events: list[StreamEvent] = []
        if text:
            events.append(StreamEvent("text", {"delta": text}))
        for idx, call in enumerate(tool_calls):
            events.append(StreamEvent("tool_call", {"index": idx, "call": call}))
        for idx, result in enumerate(tool_results):
            events.append(StreamEvent("tool_result", {"index": idx, "result": result}))
        if tool_error is not None:
            events.append(StreamEvent("error", tool_error.as_dict()))
        if usage is not None:
            events.append(StreamEvent("usage", usage))
        events.append(
            StreamEvent(
                "final",
                self._final_event_data(
                    text=text or None,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    usage=usage,
                    error=tool_error,
                ),
            )
        )
        if prepared.should_update:
            self._update_tape(
                prepared,
                text or None,
                tool_calls=tool_calls or None,
                tool_results=tool_results or None,
                error=tool_error,
                response=response,
                provider=provider_name,
                model=model_id,
                usage=usage,
            )
        return StreamEvents(iter(events), state=state)

    def _build_async_event_stream_from_response(
        self,
        prepared: PreparedChat,
        response: Any,
        provider_name: str,
        model_id: str,
    ) -> AsyncStreamEvents:
        sync_events = self._build_event_stream_from_response(
            prepared,
            response,
            provider_name,
            model_id,
        )

        async def _iterator() -> AsyncIterator[StreamEvent]:
            for event in sync_events:
                yield event

        return AsyncStreamEvents(_iterator(), state=StreamState(error=sync_events.error, usage=sync_events.usage))

    def _execute_tool_calls(
        self,
        prepared: PreparedChat,
        tool_calls: list[dict[str, Any]],
        provider_name: str,
        model_id: str,
    ) -> tuple[list[Any], ErrorPayload | None]:
        if not tool_calls:
            return [], None
        if not prepared.toolset.runnable:
            return [], ErrorPayload(ErrorKind.TOOL, "No runnable tools are available.")
        tool_context = ToolContext(
            tape=prepared.tape,
            run_id=prepared.run_id,
            meta={"provider": provider_name, "model": model_id},
            state={},
        )
        execution = self._tool_executor.execute(
            tool_calls,
            tools=prepared.toolset.runnable,
            context=tool_context,
        )
        return execution.tool_results, execution.error

    @staticmethod
    def _extract_text(response: Any) -> str:
        if isinstance(response, str):
            return response
        choices = getattr(response, "choices", None)
        if not choices:
            return ""
        message = getattr(choices[0], "message", None)
        if message is None:
            return ""
        return getattr(message, "content", "") or ""

    @staticmethod
    def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
        choices = getattr(response, "choices", None)
        if not choices:
            return []
        message = getattr(choices[0], "message", None)
        if message is None:
            return []
        tool_calls = getattr(message, "tool_calls", None) or []
        calls: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            entry: dict[str, Any] = {
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments,
                }
            }
            call_id = getattr(tool_call, "id", None)
            if call_id:
                entry["id"] = call_id
            call_type = getattr(tool_call, "type", None)
            if call_type:
                entry["type"] = call_type
            calls.append(entry)
        return calls

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, Any] | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            return usage.model_dump()
        if isinstance(usage, dict):
            return dict(usage)
        data: dict[str, Any] = {}
        for field in ("input_tokens", "output_tokens", "total_tokens", "requests"):
            value = getattr(usage, field, None)
            if value is not None:
                data[field] = value
        return data or None
