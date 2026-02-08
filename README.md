# Bub

[![Release](https://img.shields.io/github/v/release/psiace/bub)](https://github.com/psiace/bub/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/psiace/bub/main.yml?branch=main)](https://github.com/psiace/bub/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/psiace/bub)](https://github.com/psiace/bub/graphs/commit-activity)
[![License](https://img.shields.io/github/license/psiace/bub)](LICENSE)

> Bub it. Build it.

Bub is a tape-first coding agent CLI built on `republic`.

It uses a deterministic session model:
- one forward-only tape per session,
- explicit anchors/handoff for phase transitions,
- command-aware routing shared by both user input and assistant output..

## Install

```bash
git clone https://github.com/psiace/bub.git
cd bub
uv sync
```

## Configure

Create `.env` (or export environment variables):

```bash
BUB_MODEL=openrouter:qwen/qwen3-coder-next
OPENROUTER_API_KEY=your_key_here

# optional
BUB_MAX_TOKENS=1200
BUB_MAX_STEPS=20
BUB_HOME=~/.bub
BUB_SYSTEM_PROMPT=
```

Telegram:

```bash
BUB_TELEGRAM_ENABLED=true
BUB_TELEGRAM_TOKEN=123456:token
# json array or pydantic-compatible list input
BUB_TELEGRAM_ALLOW_FROM=["123456789","your_username"]
```

## Usage

Interactive CLI:

```bash
uv run bub chat
```

Telegram adapter:

```bash
uv run bub telegram
```

## Internal Commands

```text
,help
,tools
,tool.describe name=fs.read
,skills.list
,skills.describe name=friendly-python
,handoff name=phase-1 summary="done" next_steps="run tests"
,anchors
,tape.info
,tape.search query=error
,tape.reset archive=true
,quit
```

Shell command examples:

```text
,git status
, uv run pytest -q
```

## Tool/Skill View

Bub keeps a unified tool registry:
- builtin tools (`bash`, `fs.*`, `web.*`, `tape.*`, etc.),
- skill tools (`skills.*` and dynamic `skill.<name>`).

Prompt exposure is progressive:
- compact names/descriptions by default,
- expanded schema/details after selection.

## Development

```bash
uv run ruff check .
uv run mypy
uv run pytest -q
```

## License

[Apache 2.0](./LICENSE)
