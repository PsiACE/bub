# Telegram Integration

## Configure

```bash
BUB_TELEGRAM_ENABLED=true
BUB_TELEGRAM_TOKEN=123456:token
BUB_TELEGRAM_ALLOW_FROM=["123456789","your_username"]
```

## Run

```bash
uv run bub telegram
```

## Behavior

- Uses long polling.
- Each chat maps to deterministic session key: `telegram:<chat_id>`.
- Inbound text goes through the same `AgentLoop` as CLI.
- Outbound messages are dispatched through `ChannelManager`.
- Typing indicator runs while message is being processed.

## Security

- If allowlist is set, only listed user IDs/usernames can use the bot.
- If allowlist is empty, all senders are accepted.
