# Interactive CLI

## Start

```bash
uv run bub chat
```

Optional:

```bash
uv run bub chat --workspace /path/to/repo --model openrouter:openrouter/auto --max-tokens 1400
```

## Interaction Model

- Single interactive mode only.
- PromptToolkit input with history and bottom status bar.
- Shared runtime contract with channel adapters.

## Command Examples

```text
,help
,tools
,tool.describe name=fs.read
,skills.list
,handoff name=phase-x summary="done"
,tape.info
,quit
```

Shell command examples:

```text
git status
uv run pytest -q
```

## Status Bar

Bottom toolbar displays:
- current time,
- mode,
- model id,
- tape summary (`entries`, `anchors`, `last_anchor`).

## Exit

- `,quit`
- `Ctrl-D`
