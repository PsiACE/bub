# Interactive CLI

## Runtime Commands

```bash
uv run bub chat
```

Optional chat flags:

```bash
uv run bub chat \
  --workspace /path/to/repo \
  --model openrouter:qwen/qwen3-coder-next \
  --max-tokens 1400 \
  --session-id cli-main
```

Other runtime modes:

- `uv run bub run "summarize current repo status"`: one-shot message and exit.
- `uv run bub message`: run enabled message channels (Telegram/Discord).
- `uv run bub idle`: run scheduler only (no interactive CLI).

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
4. Validate: `uv run pytest -q`
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

## One-Shot Examples

```bash
uv run bub run ",help"
uv run bub run --tools fs.read,fs.glob --skills friendly-python "inspect Python layout"
uv run bub run --disable-scheduler "quick reasoning task"
```

## Troubleshooting

- `command not found`: verify whether it should be an internal command (`,help` for list).
- `bub message` exits immediately: no message channel is enabled in `.env`.
- Context is too heavy: add a handoff anchor, then reset tape when needed.
