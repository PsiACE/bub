# Architecture

## Core Components

- `BubFramework`: creates the plugin manager, loads plugins, and runs `process_inbound()`.
- `BubHookSpecs`: defines all hook contracts (`src/bub/hookspecs.py`).
- `HookRuntime`: executes hooks with sync/async compatibility helpers (`src/bub/hook_runtime.py`).
- `RuntimeEngine`: builtin model-and-tools runtime (`src/bub/builtin/engine.py`).
- `ChannelManager`: starts channels, buffers inbound messages, and routes outbound messages (`src/bub/channels/manager.py`).

## Turn Lifecycle

`BubFramework.process_inbound()` currently executes in this order:

1. Populate inbound `workspace` when inbound is a `dict`.
2. `resolve_session(message)` via `call_first` (fallback to `channel:chat_id` if empty).
3. `load_state(message, session_id)` via `call_many`, then merge returned state dicts.
4. `build_prompt(message, session_id, state)` via `call_first` (fallback to inbound `content` if empty).
5. `run_model(prompt, session_id, state)` via `call_first`.
6. `save_state(...)` via `call_many` in a `finally` block.
7. `render_outbound(...)` via `call_many`, then flatten all batches.
8. If no outbound exists, emit one fallback outbound.
9. For each outbound, execute `dispatch_outbound(message)` via `call_many`.

## Hook Priority Semantics

- Registration order:
1. Builtin plugin `builtin`
2. External entry points (`group="bub"`)
- Execution order:
1. `HookRuntime` reverses pluggy implementation order, so later-registered plugins run first.
2. `call_first` returns the first non-`None` value.
3. `call_many` collects every implementation return value (including `None`).
- Merge/override details:
1. `load_state` is reversed again before merge so high-priority plugins win on key collisions.
2. `provide_channels` is reversed in `ChannelManager`, so high-priority plugins can override channel names.

## Error Behavior

- For normal hooks, `HookRuntime` does not swallow implementation errors.
- `process_inbound()` catches top-level exceptions, notifies `on_error(stage="turn", ...)`, then re-raises.
- `on_error` itself is observer-safe: one failing observer does not block the others.
- In sync calls (`call_first_sync`/`call_many_sync`), awaitable return values are skipped with a warning.

## Builtin Runtime Notes

Builtin `BuiltinImpl` behavior includes:

- `build_prompt`: supports comma command mode; non-command text may include `context_str`.
- `run_model`: delegates to `RuntimeEngine.run()`.
- `system_prompt`: combines a default prompt with workspace `AGENTS.md`.
- `provide_tools`: returns builtin tools.
- `provide_channels`: returns `telegram` and `cli` channel adapters.
- `provide_tape_store`: returns a file-backed tape store under `~/.bub/tapes`.

## Boundaries

- `Envelope` stays intentionally weakly typed (`Any` + accessor helpers).
- There is no globally enforced schema for cross-plugin `state`.
- Runtime behavior in this document is aligned with current source code.
