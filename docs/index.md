# Bub

Bub is a hook-first AI framework for running agent workflows through CLI and message channels.

## Quick Start

Install dependencies and create local config:

```bash
git clone https://github.com/bubbuild/bub.git
cd bub
uv sync
cp env.example .env
```

Run interactive local chat:

```bash
uv run bub chat
```

Run a one-shot task:

```bash
uv run bub run "summarize this repository"
```

Start channel listener mode:

```bash
uv run bub gateway
```

## Deployment

For production setup and operations, read:

- [Deployment Guide](deployment.md)
- [Channels Overview](channels/index.md)
- [Telegram Channel](channels/telegram.md)

## Read Next

- [Core Overview](core/index.md): architecture and capability summary in one place
- [Workflows Overview](workflows/index.md): CLI and skills usage in one place
- [Extension Guide](extension-guide.md): build and publish hook-based extensions
- [Posts](posts/index.md): project notes and updates
