# Discord Integration

Discord allows Bub to run as a remote coding assistant for team channels, threads, and DMs.

## Configure

```bash
BUB_DISCORD_ENABLED=true
BUB_DISCORD_TOKEN=discord_bot_token
BUB_DISCORD_ALLOW_FROM='["123456789012345678","your_discord_name"]'
BUB_DISCORD_ALLOW_CHANNELS='["123456789012345678"]'
```

Optional:

```bash
BUB_DISCORD_COMMAND_PREFIX=!
BUB_DISCORD_PROXY=http://127.0.0.1:7890
```

Notes:

- If `BUB_DISCORD_ALLOW_FROM` is empty, all senders are accepted.
- If `BUB_DISCORD_ALLOW_CHANNELS` is empty, all channels are accepted.
- In production, use strict allowlists.

## Run

```bash
uv run bub message
```

## Runtime Behavior

- Uses `discord.py` bot runtime.
- Each Discord channel maps to `discord:<channel_id>` session key.
- Inbound text enters the same `AgentLoop` used by CLI.
- Outbound immediate output is sent back in-channel (split into chunks when too long).
- Bub processes messages in these cases:
  - DM channel
  - message includes `bub`
  - message starts with `!bub` (or your configured prefix)
  - message mentions the bot
  - message replies to a bot message
  - thread name starts with `bub`

## Security and Operations

1. Keep bot token only in `.env` or a secret manager.
2. Restrict `BUB_DISCORD_ALLOW_CHANNELS` and `BUB_DISCORD_ALLOW_FROM`.
3. Confirm the bot has message-content intent enabled in Discord Developer Portal.
4. If no response is observed, verify token, allowlists, intents, and runtime logs.
