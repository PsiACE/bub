# Deployment Guide

This page covers production-oriented setups for Bub, including local process management and Docker Compose.

## 1) Prerequisites

- Python 3.12+
- `uv` installed
- A valid model provider key (for example `OPENROUTER_API_KEY` or `LLM_API_KEY`)

Quick bootstrap:

```bash
git clone https://github.com/psiace/bub.git
cd bub
uv sync
cp env.example .env
```

Minimum `.env`:

```bash
BUB_MODEL=openrouter:qwen/qwen3-coder-next
OPENROUTER_API_KEY=sk-or-...
```

## 2) Deployment Modes

Choose one mode based on your operation target:

1. Interactive local operator:
   `uv run bub chat`
2. Channel service (Telegram/Discord):
   `uv run bub message`
3. Scheduler-only autonomous runtime:
   `uv run bub idle`

One-shot operation:

```bash
uv run bub run "summarize changes in this repo"
```

## 3) Message Channel Deployment

Enable channels in `.env` first.

Telegram:

```bash
BUB_TELEGRAM_ENABLED=true
BUB_TELEGRAM_TOKEN=123456:token
BUB_TELEGRAM_ALLOW_FROM='["123456789","your_username"]'
BUB_TELEGRAM_ALLOW_CHATS='["123456789","-1001234567890"]'
```

Discord:

```bash
BUB_DISCORD_ENABLED=true
BUB_DISCORD_TOKEN=discord_bot_token
BUB_DISCORD_ALLOW_FROM='["123456789012345678","your_discord_name"]'
BUB_DISCORD_ALLOW_CHANNELS='["123456789012345678"]'
```

Start channel service:

```bash
uv run bub message
```

## 4) Docker Compose Deployment

The repository already provides `Dockerfile`, `docker-compose.yml`, and `entrypoint.sh`.

Build and run:

```bash
docker compose up -d --build
docker compose logs -f app
```

Behavior in container:

- If `/workspace/startup.sh` exists, container starts `bub idle` in background, then executes `startup.sh`.
- Otherwise, container starts `bub message`.

Default mounts in `docker-compose.yml`:

- `${BUB_WORKSPACE_PATH:-.}:/workspace`
- `${BUB_HOME:-${HOME}/.bub}:/data`
- `${BUB_AGENT_HOME:-${HOME}/.agent}:/root/.agent`

## 5) Operational Checks

Health checklist:

1. Process is running:
   `ps aux | rg "bub (chat|message|idle)"`
2. Model key is loaded:
   `rg -n "BUB_MODEL|OPENROUTER_API_KEY|LLM_API_KEY" .env`
3. Channel flags are correct:
   `rg -n "BUB_TELEGRAM_ENABLED|BUB_DISCORD_ENABLED" .env`
4. Logs show channel startup:
   `uv run bub message` and confirm `channel.manager.start` output.

## 6) Safe Upgrade Procedure

```bash
git fetch --all --tags
git pull
uv sync
uv run ruff check .
uv run mypy
uv run pytest -q
```

Then restart your runtime (`chat`, `message`, or container service).
