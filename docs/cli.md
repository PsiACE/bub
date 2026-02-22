# CLI

## Run one message

```bash
uv run bub run "hello" --channel stdout --chat-id local
```

## Run with runtime mode

```bash
BUB_RUNTIME_ENABLED=1 uv run bub run "summarize current repo status"
```

## Command-style runtime input

```bash
BUB_RUNTIME_ENABLED=1 uv run bub run ",help"
```

## List skills

```bash
uv run bub skills
```

This command shows discovered skills and their current runtime health.

## List hook bindings

```bash
uv run bub hooks
```

## Notes

- `--workspace` is supported on `run`, `skills`, and `hooks`
- If runtime model is unavailable, `bub run` still returns a safe textual result
- Session identity falls back to `channel:chat_id` when not provided explicitly
