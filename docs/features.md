# Key Features

This page summarizes the capabilities users rely on most when working with Bub.

## 1. Deterministic Command Routing

- Command mode is explicit: only line-start `,` triggers command parsing.
- Known names map to internal commands (for example `,help`, `,tools`, `,tape.info`).
- Other comma-prefixed lines run as shell commands (for example `,git status`).

Why it matters: fewer accidental tool calls and more predictable behavior.

## 2. Command Failure Recovery

- Successful commands return directly.
- Failed commands are wrapped as structured command blocks and sent back to the model loop.

Why it matters: the assistant can debug based on real command output instead of generic guesses.

## 3. Tape-First Session Memory

- Bub writes session activity to append-only tape.
- `,anchors` and `,handoff` mark phase transitions.
- `,tape.search` and `,tape.info` help inspect context quickly.

Why it matters: long tasks stay traceable and easier to resume.

## 4. Persistent Memory Zone

- Long-term memory and daily notes live inside the tape as a versioned zone.
- Memory is automatically injected into the system prompt.
- Quick access via shortcuts: `,memory`, `,memory.save`, `,memory.daily`, `,memory.recall`, `,memory.clear`.
- The LLM proactively saves user preferences and logs work progress.

Why it matters: the assistant remembers context across sessions without manual configuration.

## 5. Unified Tool + Skill View

- Built-in tools and skills share one registry.
- Prompt includes compact tool descriptions first.
- Tool details expand on explicit selection (for example `,tool.describe name=fs.read`).
- `$name` hints expand details progressively for both tools and skills.
- Hints can come from user input or model output (for example `$fs.read`, `$friendly-python`).

Why it matters: prompt stays focused while advanced capabilities remain available on demand.

## 6. Interactive CLI Focused on Real Work

- Rich interactive shell with history and completions.
- `Ctrl-X` toggles shell mode for faster command execution.
- Same runtime behavior as channel integrations.

Why it matters: local debugging and implementation loops are fast and consistent.

## 7. Telegram Channel Integration

- Optional long-polling Telegram adapter.
- Per-chat session isolation (`telegram:<chat_id>`).
- Optional sender allowlist for access control.

Why it matters: you can continue lightweight operations from mobile or remote environments.
