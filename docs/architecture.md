# Architecture

## Core Components

- `BubFramework`: creates the plugin manager, loads hooks, runs turns
- `BubHookSpecs`: defines hook contracts (`firstresult` and broadcast hooks)
- `HookRuntime`: executes hook implementations with per-impl fault isolation
- `MessageBus`: default in-memory bus (replaceable via hook)

## Turn Lifecycle

`process_inbound()` executes hooks in this order:

1. `normalize_inbound(message)`
2. `resolve_session(message)`
3. `load_state(session_id)` (defaults to `{}`)
4. `build_prompt(message, session_id, state)` (defaults to message `content`)
5. `run_model(prompt, session_id, state)`
6. `save_state(...)` (broadcast)
7. `render_outbound(...)` (broadcast)
8. `dispatch_outbound(message)` (broadcast per outbound)

If `render_outbound` yields nothing, the framework emits one fallback outbound:

```text
{
  "content": model_output,
  "session_id": session_id,
  "channel": ...?,   # if exists in inbound
  "chat_id": ...?    # if exists in inbound
}
```

## Precedence And Override Semantics

- Hook registration order:
  1. Builtin plugin `bub.builtin.hook_impl`
  2. External entry points (`group="bub"`)
- Execution order: `HookRuntime` reverses pluggy impl order, so later-registered plugins run first
- For `firstresult` hooks: first non-`None` value wins
- For broadcast hooks (for example `save_state`): all implementations are attempted

## Fault Isolation And Fallbacks

- A failing hook implementation does not crash the whole turn; `on_error` is notified
- If `run_model` returns no value, fallback is `model_output = prompt`
- `create_bus()` falls back to `MessageBus` when no plugin provides a bus
- `handle_bus_once()` consumes one inbound from bus and publishes produced outbounds

## Builtin Runtime

Builtin `run_model` is implemented by `RuntimeEngine`:

- Regular prompts run through Republic `run_tools_async`
- Comma-prefixed input goes through internal command dispatch (`help/tools/fs.*/...`)
- Unknown comma commands are executed as shell commands
- Runtime events are persisted at `.bub/runtime/<session-hash>.jsonl`

## Boundaries

- `Envelope` is intentionally weakly typed (`Any`) and read via helper accessors
- There is no global enforced business schema for messages or cross-plugin state
- Skill discovery/validation is a separate subsystem (see `skills.md`)
