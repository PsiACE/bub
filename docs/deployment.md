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
2. Channel listener service: `uv run bub gateway`
3. One-shot task execution: `uv run bub run "summarize this repo"`

## 3) Telegram Channel Setup

Telegram configuration and runtime behavior are documented in:

- `docs/channels/telegram.md`

Quick start:

```bash
BUB_TELEGRAM_TOKEN=123456:token uv run bub gateway --enable-channel telegram
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

- if `/workspace/startup.sh` exists, entrypoint tries to run `startup.sh`
- otherwise it starts `bub gateway`

Default mounts in `docker-compose.yml`:

- `${BUB_WORKSPACE_PATH:-.}:/workspace`
- `${BUB_HOME:-${HOME}/.bub}:/data`
- `${BUB_AGENT_HOME:-${HOME}/.agents}:/root/.agents`

Notes:

- Bub runtime data is written under `BUB_HOME` (container default: `/root/.bub`).
- In this compose file, `BUB_HOME` is used as the host bind source for `/data`.
- Do not set `BUB_HOME=/data` directly in `.env` with this compose file, or the host bind source will also become `/data`.
- If you want Bub runtime home to be `/data` in container, split variables first (for example `BUB_HOME_HOST` for host path) and then set `BUB_HOME=/data`.

## 5) Operational Checks

1. Verify process:
   `ps aux | rg "bub (chat|gateway|run)"`
2. Verify model config:
   `rg -n "BUB_MODEL|BUB_API_KEY|BUB_API_BASE|BUB_.*_API_KEY|BUB_.*_API_BASE|OPENROUTER_API_KEY" .env`
3. Verify Telegram settings:
   `rg -n "BUB_TELEGRAM_TOKEN|BUB_TELEGRAM_ALLOW_USERS|BUB_TELEGRAM_ALLOW_CHATS" .env`
4. Verify startup logs:
   `uv run bub gateway --enable-channel telegram`

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
