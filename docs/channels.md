# Channels

Bub supports running the same agent loop through message channels.
Use channels when you want remote operation from mobile or shared team environments.

## Supported Channels

- [Telegram](telegram.md): direct messages and group chats.
- [Discord](discord.md): servers, channels, and threads.

## Runtime Entry

Start channel runtime with:

```bash
uv run bub message
```

If the process exits immediately, check that at least one channel is enabled in `.env`.

## Session Isolation

- Telegram session key: `telegram:<chat_id>`
- Discord session key: `discord:<channel_id>`

This keeps message history isolated per conversation endpoint.
