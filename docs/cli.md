# CLI

`bub` currently exposes four builtin commands: `run`, `hooks`, `message`, and `chat`.

## `bub run`

Run one inbound message through the full framework pipeline and print outbounds.

```bash
uv run bub run "hello" --channel cli --chat-id local
```

Common options:

- `--workspace/-w`: workspace root
- `--channel`: source channel (default `cli`)
- `--chat-id`: source endpoint id (default `local`)
- `--sender-id`: sender identity (default `human`)
- `--session-id`: explicit session id (default is `<channel>:<chat_id>`)

Comma-prefixed input enters internal command mode:

```bash
uv run bub run ",help"
uv run bub run ",tools"
uv run bub run ",fs.read path=README.md"
```

Unknown comma commands fall back to shell execution:

```bash
uv run bub run ",echo hello-from-shell"
```

## `bub hooks`

Print hook-to-plugin bindings discovered at startup.

```bash
uv run bub hooks
```

## `bub message`

Start channel listener mode (defaults to all non-`cli` channels).

```bash
uv run bub message
```

Enable only selected channels:

```bash
uv run bub message --enable-channel telegram
```

## `bub chat`

Start an interactive REPL session via the `cli` channel.

```bash
uv run bub chat
uv run bub chat --chat-id local --session-id cli:local
```

## Notes

- `--workspace` is supported by `run`, `hooks`, `message`, and `chat`.
- `run` prints each outbound as:

```text
[channel:chat_id]
content
```
