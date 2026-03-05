# Feishu Integration

Feishu allows Bub to run as a remote collaboration endpoint through a WebSocket event stream.

## Configure

```bash
BUB_FEISHU_ENABLED=true
BUB_FEISHU_APP_ID=cli_xxx
BUB_FEISHU_APP_SECRET=xxx
BUB_FEISHU_ALLOW_FROM='["ou_xxx","user@example.com"]'
BUB_FEISHU_ALLOW_CHATS='["oc_xxx"]'
```

Notes:

- If `BUB_FEISHU_ALLOW_FROM` is empty, all senders are accepted.
- If `BUB_FEISHU_ALLOW_CHATS` is empty, all chats are accepted.
- In production, use strict allowlists.

## Run

```bash
uv run bub message
```

## Run Behavior

- Uses WebSocket subscription for inbound Feishu events.
- Group chats map to `feishu:<chat_id>` session key.
- 1:1 chats map to `feishu:<open_id>` session key.
- Inbound messages enter the same `AgentLoop` used by CLI/Telegram/Discord.
- `,` command boundary is unchanged (`,help` / `,git status` / natural language).

## Security and Operations

1. Keep `BUB_FEISHU_APP_SECRET` only in `.env` or a secret manager.
2. Restrict both `BUB_FEISHU_ALLOW_FROM` and `BUB_FEISHU_ALLOW_CHATS`.
3. Use a dedicated Feishu app for Bub; avoid sharing app credentials across services.
4. Validate reconnect behavior in logs after network interruptions.
5. If `uv run bub message` exits quickly, verify at least one channel is enabled.
