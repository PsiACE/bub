# Deployment Guide

This page covers practical Bub deployment paths based on the current repository behavior.

## 1) Prerequisites

- Python 3.12+
- `uv` installed
- a valid model provider key (for example `OPENROUTER_API_KEY`)

Bootstrap:

```bash
git clone https://github.com/bubbuild/bub.git
cd bub
uv sync
cp env.example .env
```

Minimum `.env` example:

```bash
BUB_MODEL=openrouter:qwen/qwen3-coder-next
OPENROUTER_API_KEY=sk-or-...
```

## 2) Runtime Modes

Choose one command based on your operation target:

1. Interactive local operator: `uv run bub chat`
2. Channel listener service: `uv run bub message`
3. One-shot task execution: `uv run bub run "summarize this repo"`

## 3) Telegram Channel Setup

Current core channel integration is Telegram.

Required:

```bash
BUB_TELEGRAM_TOKEN=123456:token
```

Optional allowlists (comma-separated values):

```bash
BUB_TELEGRAM_ALLOW_USERS=123456789,your_username
BUB_TELEGRAM_ALLOW_CHATS=123456789,-1001234567890
```

Optional proxy:

```bash
BUB_TELEGRAM_PROXY=http://127.0.0.1:7890
```

Run listener:

```bash
uv run bub message --enable-channel telegram
```

## 4) Docker Compose

Repository assets:

- `Dockerfile`
- `docker-compose.yml`
- `entrypoint.sh`

Build and run:

```bash
docker compose up -d --build
docker compose logs -f app
```

Current entrypoint behavior:

- if `/workspace/startup.sh` exists, entrypoint tries to start `bub idle` in background, then runs `startup.sh`
- otherwise it starts `bub message`

Important: core CLI currently does not expose a builtin `idle` command. If you rely on `startup.sh`, verify your image/plugin setup provides it, or adjust `entrypoint.sh`.

Default mounts in `docker-compose.yml`:

- `${BUB_WORKSPACE_PATH:-.}:/workspace`
- `${BUB_HOME:-${HOME}/.bub}:/data`
- `${BUB_AGENT_HOME:-${HOME}/.agent}:/root/.agent`

## 5) Operational Checks

1. Verify process:
   `ps aux | rg "bub (chat|message|run)"`
2. Verify model config:
   `rg -n "BUB_MODEL|OPENROUTER_API_KEY|LLM_API_KEY" .env`
3. Verify Telegram settings:
   `rg -n "BUB_TELEGRAM_TOKEN|BUB_TELEGRAM_ALLOW_USERS|BUB_TELEGRAM_ALLOW_CHATS" .env`
4. Verify startup logs:
   `uv run bub message --enable-channel telegram`

## 6) Safe Upgrade

```bash
git fetch --all --tags
git pull
uv sync
uv run ruff check .
uv run mypy
uv run pytest -q
```

Then restart your service command.
