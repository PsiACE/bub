# Channels

Bub supports running the same agent loop through channel adapters.
Use channels when you want either local interactive operation or remote operation from mobile/shared team environments.

## Supported Channels

- `cli` (local): interactive terminal channel used by `uv run bub chat`.
- [Telegram](telegram.md): direct messages and group chats.
- [Discord](discord.md): servers, channels, and threads.

## Run Entry

Start channel mode with:

```bash
uv run bub message
```

If the process exits immediately, check that at least one channel is enabled in `.env`.

## Session Isolation

- CLI session key: `cli` or `cli:<name>` (from `--session-id`).
- Telegram session key: `telegram:<chat_id>`
- Discord session key: `discord:<channel_id>`

This keeps message history isolated per conversation endpoint.

## Runtime Semantics

- `uv run bub chat` runs `CliChannel` via `ChannelManager`, sharing the same channel pipeline as Telegram/Discord.
- CLI sets `debounce_enabled = False`, so each input is processed immediately.
- Message channels keep debounce enabled to batch short bursts before model execution.
