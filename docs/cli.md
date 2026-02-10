# Interactive CLI

## Start

```bash
uv run bub
```

Optional:

```bash
uv run bub chat --workspace /path/to/repo --model openrouter:qwen/qwen3-coder-next --max-tokens 1400
```

## How Input Is Interpreted

- Only lines starting with `,` are interpreted as commands.
- Registered names like `,help` are internal commands.
- Other comma-prefixed lines run through shell, for example `,git status`.
- Non-comma input is always treated as natural language.

This rule is shared by both user input and assistant output.

## Shell Mode

Press `Ctrl-X` to toggle between `agent` and `shell` mode.

- `agent` mode: send input as typed.
- `shell` mode: if input does not start with `,`, Bub auto-normalizes it to `, <your command>`.

Use shell mode when you want to run multiple shell commands quickly.

## Typical Workflow

1. Check repo status: `,git status`
2. Read files: `,fs.read path=README.md`
3. Edit files: `,fs.edit path=foo.py old=... new=...`
4. Validate: `,uv run pytest -q`
5. Mark phase transition: `,handoff name=phase-x summary="tests pass"`

## Session Context Commands

```text
,tape.info
,tape.search query=error
,anchors
,tape.reset archive=true
```

- `,tape.reset archive=true` archives then clears current tape.
- `,anchors` shows phase boundaries.

## Memory Commands

```text
,memory                                    Show memory summary
,memory.save content='User prefers dark mode'
,memory.daily content='Fixed tape reset bug'
,memory.recall days=7
,memory.recall query=python
,memory.clear
```

- `,memory` is a shortcut for `,memory.show`.
- Long-term memory persists across sessions and is injected into the system prompt.
- Daily notes are timestamped and auto-pruned after 30 days.

## Troubleshooting

- `command not found`: verify whether it should be an internal command (`,help` for list).
- Verbose or odd output: Bub may still be processing command follow-up context.
- Context is too heavy: add a handoff anchor, then reset tape when needed.
