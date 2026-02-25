# CLI

`bub` currently exposes three commands: `run`, `hooks`, and `install`.

## `bub run`

Run one inbound message through the full framework lifecycle.

```bash
uv run bub run "hello" --channel stdout --chat-id local
```

When runtime is disabled or unavailable, output safely falls back to the input prompt text:

```bash
BUB_RUNTIME_ENABLED=0 uv run bub run "hello"
```

Run with runtime enabled:

```bash
BUB_RUNTIME_ENABLED=1 BUB_API_KEY=your_key uv run bub run "summarize current repo status"
```

Comma-prefixed inputs invoke internal command mode:

```bash
BUB_RUNTIME_ENABLED=0 uv run bub run ",help"
BUB_RUNTIME_ENABLED=0 uv run bub run ",tools"
BUB_RUNTIME_ENABLED=0 uv run bub run ",fs.read path=README.md"
```

Unknown comma commands are executed as shell commands:

```bash
BUB_RUNTIME_ENABLED=0 uv run bub run ",echo hello-from-shell"
```

## `bub hooks`

Print hook-to-plugin bindings discovered at startup.

```bash
uv run bub hooks
```

## `bub install`

Install plugins from PyPI requirement spec or GitHub shorthand.

```bash
uv run bub install my-plugin-package
uv run bub install owner/repo
```

`owner/repo` is converted to:

```text
git+https://github.com/owner/repo.git
```

## Notes

- `--workspace` is supported by `run` and `hooks`
- `BUB_RUNTIME_ENABLED` supports `0`, `1`, and `auto` (default)
- Session id defaults to `channel:chat_id` when `--session-id` is not provided
- `run` prints each outbound as `[channel:chat_id] content`
