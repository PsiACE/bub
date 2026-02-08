# Bub Docs

Bub is built for day-to-day coding tasks: run commands, edit files, debug failures, and keep progress visible across long sessions.

## What You Can Expect

- Clear command behavior: only lines that start with `,` are commands.
- One execution path: the same rules apply to both your input and assistant-generated commands.
- Graceful recovery: failed commands are fed back to the model with structured context.
- Trackable sessions: tape, anchors, and handoff help you resume work cleanly.

## How Bub Behaves In Practice

1. Type normal text to ask the assistant.
2. Start a line with `,` to run a command.
3. Known names such as `,help` are internal commands.
4. Other comma-prefixed lines are treated as shell commands.
5. If a command fails, Bub keeps going and uses the error context in the next model step.

## Start Here

- [Key Features](features.md)
- [Interactive CLI](cli.md)
- [Architecture](architecture.md)
- [Telegram Integration](telegram.md)

## Common Commands

```text
,help
,tools
,tool.describe name=fs.read
,tape.info
,tape.search query=timeout
,handoff name=phase-2 summary="router fixed" next_steps="run pytest"
,anchors
,tape.reset archive=true
```

## Configuration

Start from `env.example` in the repository root.
Use model + API key first, then add Telegram and advanced settings when needed.
