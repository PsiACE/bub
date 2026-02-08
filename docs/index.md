# Bub Docs

## What Bub Is

Bub is a tape-first coding agent runtime:
- deterministic, forward-only session flow,
- explicit anchors and handoff for phase transitions,
- shared command router for user and assistant outputs.

## Core Rules

1. Internal commands use `,` prefix.
2. Shell commands run through `bash` tool.
3. Command success returns directly; command failure falls back to model.
4. `$` is hint-only for potential tool/skill usage.
5. Tape is append-only; no runtime fork/rollback semantics.

## Read Next

- [Architecture](architecture.md)
- [Interactive CLI](cli.md)
- [Telegram Integration](telegram.md)
- [Rewrite Plan (tracking)](rewrite-plan-2026-02.md)
