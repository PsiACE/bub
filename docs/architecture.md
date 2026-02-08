# Architecture

## Design Goal

Bub uses one endless tape per session and keeps behavior inspectable:
- facts are appended, never rewritten,
- runtime state is rebuilt from anchors,
- handoff marks phase transitions with minimal structured state.

## Runtime Topology

```text
input -> InputRouter -> AgentLoop -> ModelRunner -> InputRouter(assistant output) -> ...
                    \-> direct command response
```

Main modules:

- `bub.app.runtime`: workspace runtime + per-session runtime creation.
- `bub.core.router`: command detection/execution for user and assistant outputs.
- `bub.core.agent_loop`: turn orchestration.
- `bub.core.model_runner`: bounded model loop and follow-up command context.
- `bub.tape.*`: persistent tape store and handoff/anchor helpers.

## Tape and Anchors

Tape store:
- file-backed JSONL per workspace + session tape name.
- append-only `TapeEntry`.

Anchor usage:
- bootstrap anchor is created once (`session/start`).
- `,handoff` writes anchor with optional `summary` and `next_steps`.
- context selection is `LAST_ANCHOR` by default.

## Tool and Skill Unification

All capabilities are exposed via one registry:
- builtin tools (`bash`, `fs.*`, `web.*`, `tape.*`, control commands),
- skill tools:
  - `skills.list`
  - `skills.describe`
  - dynamic `skill.<skill_name>`.

Progressive exposure:
- system prompt includes compact tool list,
- detailed schema is expanded after selection (`tool.describe` / invocation).

## Agent Loop Contract

Per user turn:
1. Route user input.
2. Parse comma-prefixed commands in router:
   internal command if known name, otherwise shell command.
3. If command success: return.
4. If command failure or NL input: enter model loop.
5. Parse assistant output with same router.
6. If assistant emitted commands: execute and feed command blocks into next model step.
7. Stop on plain final text, explicit quit, or `max_steps`.

Routing note:
- Only line-start `,` is considered command prefix.
- Non-prefixed text is always treated as natural language.

## Channel Integration

`blinker` signal bus:
- inbound signal -> runtime handle_input,
- outbound signal -> channel adapter send.

Current external adapter:
- Telegram long polling (`python-telegram-bot`).
