# Bub Docs

Bub is a collaborative agent for shared delivery workflows, evolving into a framework that helps other agents operate with the same collaboration model.
If you only remember one thing from this page, remember this: Bub is built for shared delivery workflows where execution must be inspectable, handoff-friendly, and repeatable.

Under the hood, Bub uses [Republic](https://github.com/bubbuild/republic) to assemble context from traceable history instead of inheriting opaque state.
Its operating philosophy follows [Socialized Evaluation](https://psiace.me/posts/im-and-socialized-evaluation/): quality is judged by whether teams can inspect decisions and continue work safely.

## What Bub Is (and Is Not)

- Bub is a collaboration agent for human and agent operators.
- Bub is not a personal-assistant-only chat shell.
- Bub keeps command execution explicit, reviewable, and recoverable.

## How Bub Works

1. Input boundary: only lines starting with `,` are treated as commands.
2. Unified routing: the same routing rules apply to user input and assistant output.
3. Structured fallback: failed commands are returned to the model with execution evidence.
4. Persistent evidence: interaction history is append-only (`tape`) and can be searched.
5. Explicit transitions: `anchor` and `handoff` represent phase changes and responsibility transfer.

## Checklist

1. Start with model + API key in `.env`.
2. Run `uv run bub` and ask a normal question.
3. Run `,help` and `,tools` to inspect available capabilities.
4. Execute one shell command like `,git status`.
5. Create one handoff: `,tape.handoff name=phase-1 summary="..."`.
6. Verify history using `,tape.info` or `,tape.search query=...`.

## Where To Read Next

- [Key Features](features.md): capability-level overview.
- [Interactive CLI](cli.md): interactive workflow and troubleshooting.
- [Architecture](architecture.md): runtime boundaries and internals.
- [Deployment Guide](deployment.md): local and Docker operations.
- [Channels](channels.md): CLI/Telegram/Discord runtime model.
- [Post: Socialized Evaluation and Agent Partnership](posts/2026-03-01-bub-socialized-evaluation-and-agent-partnership.md): project position and principles.
