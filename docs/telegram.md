# Telegram Integration

Telegram allows Bub to run as a remote coding assistant entry point for lightweight operations.

## Configure

```bash
BUB_TELEGRAM_ENABLED=true
BUB_TELEGRAM_TOKEN=123456:token
BUB_TELEGRAM_ALLOW_FROM=["123456789","your_username"]
```

Notes:

- If `BUB_TELEGRAM_ALLOW_FROM` is empty, all senders are accepted.
- In production, use a strict allowlist.

## Run

```bash
uv run bub telegram
```

## Runtime Behavior

- Uses long polling.
- Each Telegram chat maps to `telegram:<chat_id>` session key.
- Inbound text enters the same `AgentLoop` used by CLI.
- Outbound messages are sent by `ChannelManager`.
- Typing indicator is emitted while processing.

## Security and Operations

1. Keep bot token only in `.env` or a secret manager.
2. Use a dedicated bot account.
3. Keep allowlist updated with valid user IDs/usernames.
4. If no response is observed, check network, token, then runtime/model logs.
