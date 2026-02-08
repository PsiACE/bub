# Bub Docs

## What Bub Is

Bub is a tape-first coding agent runtime:
- deterministic, forward-only session flow,
- explicit anchors and handoff for phase transitions,
- shared command router for user and assistant outputs.

## Core Rules

1. Commands are recognized only when line starts with `,`.
2. Known command names map to internal tools (for example: `,help`, `,tools`, `,tape.info`).
3. Other comma-prefixed lines run as shell through `bash` tool (for example: `,git status`).
4. Command success returns directly; command failure falls back to model with structured command context.
5. Tape is append-only; no runtime fork/rollback semantics.

## Read Next

- [Architecture](architecture.md)
- [Interactive CLI](cli.md)
- [Telegram Integration](telegram.md)
