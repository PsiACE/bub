# CLI

## Run one message

```bash
uv run bub run "hello" --channel stdout --chat-id local
```

## Force Republic model runtime

```bash
BUB_RUNTIME_ENABLED=1 uv run bub run "summarize current repo status"
```

## Command-compatible mode through runtime

```bash
BUB_RUNTIME_ENABLED=1 uv run bub run ",help"
```

## List skills

```bash
uv run bub skills
```

## List hook bindings

```bash
uv run bub hooks
```

## Notes

- If Republic model runtime is unavailable (for example no API key), `bub run` still works and returns prompt text.
- Session identity defaults to `channel:chat_id` unless `--session-id` is provided.
