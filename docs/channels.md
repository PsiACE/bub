# Channels

Bub uses channel adapters to run the same agent pipeline across different I/O endpoints.

## Builtin Channels

- `cli`: local interactive terminal channel (`uv run bub chat`)
- `telegram`: Telegram bot channel (`uv run bub message`)

## Run Modes

Local interactive mode:

```bash
uv run bub chat
```

Channel listener mode (all non-`cli` channels by default):

```bash
uv run bub message
```

Enable only Telegram:

```bash
uv run bub message --enable-channel telegram
```

## Session Semantics

- `run` command default session id: `<channel>:<chat_id>`
- Telegram channel session id: `telegram:<chat_id>`
- `chat` command default session id: `cli_session` (override with `--session-id`)

## Debounce Behavior

- `cli` does not debounce; each input is processed immediately.
- Other channels can debounce and batch inbound messages per session.
- Comma commands (`,` prefix) always bypass debounce and execute immediately.

## About Discord

Core Bub does not currently include a builtin Discord adapter.
If you need Discord, implement it in an external plugin via `provide_channels`.

## Telegram Configuration

Environment variables are read by `TelegramSettings` (`src/bub/channels/telegram.py`).

Required:

```bash
BUB_TELEGRAM_TOKEN=123456:token
```

Optional allowlists (comma-separated):

```bash
BUB_TELEGRAM_ALLOW_USERS=123456789,your_username
BUB_TELEGRAM_ALLOW_CHATS=123456789,-1001234567890
```

Optional proxy:

```bash
BUB_TELEGRAM_PROXY=http://127.0.0.1:7890
```

## Telegram Message Behavior

- Session id is `telegram:<chat_id>`.
- `/start` is handled by builtin channel logic.
- `/bub ...` is accepted and normalized to plain prompt content.
- Non-command messages are ingested; active/follow-up behavior is decided by channel filter metadata plus debounce handling.

## Telegram Outbound Behavior

- Outbound is sent back to Telegram chat via bot API.
- Empty outbound text is ignored.
- If outbound content is JSON, the `"message"` field is used when present.

## Telegram Access Control

- If `BUB_TELEGRAM_ALLOW_CHATS` is set, non-listed chats are ignored.
- If `BUB_TELEGRAM_ALLOW_USERS` is set, non-listed users are denied.
- In group chats, keep allowlists strict for production bots.
