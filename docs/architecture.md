# Architecture

This page is for developers and advanced users who need to understand why Bub behavior is deterministic and how to extend it safely.

## Core Principles

1. One session, one append-only tape.
2. Same routing rules for user input and assistant output.
3. Command execution and model reasoning are explicit layers.
4. Phase transitions are represented by `anchor/handoff`, not hidden state jumps.

## Runtime Topology

```text
input -> InputRouter -> AgentLoop -> ModelRunner -> InputRouter(assistant output) -> ...
                \-> direct command response
```

Key modules:

- `src/bub/core/router.py`: command detection, execution, and failure context wrapping.
- `src/bub/core/agent_loop.py`: turn orchestration and stop conditions.
- `src/bub/core/model_runner.py`: bounded model loop and user-driven skill-hint activation.
- `src/bub/tape/service.py`: tape read/write, anchor/handoff, reset, and search.
- `src/bub/tools/*`: unified registry and progressive tool view.

## Single Turn Flow

1. `InputRouter.route_user` checks whether input starts with `,`.
2. If command succeeds, return output directly.
3. If command fails, generate a `<command ...>` block for model context.
4. `ModelRunner` gets assistant output.
5. `route_assistant` applies the same command parsing/execution rules.
6. Loop ends on plain final text, explicit quit, or `max_steps`.

## Tape, Anchor, Handoff

- Tape is workspace-level JSONL for replay and audit.
- `handoff` writes an anchor with optional `summary` and `next_steps`.
- `anchors` lists phase boundaries.
- `tape.reset` clears active context (optionally archiving first).

## Tools and Skills

- Built-in tools and skills live in one registry.
- System prompt starts with compact tool descriptions.
- Full tool schema is expanded on demand (`tool.describe` or explicit selection).
- `$name` hints progressively expand tool/skill details from either user input or model output.
