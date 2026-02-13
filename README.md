# Bub

[![Release](https://img.shields.io/github/v/release/bubbuild/bub)](https://github.com/bubbuild/bub/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/bubbuild/bub/main.yml?branch=main)](https://github.com/bubbuild/bub/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/bubbuild/bub)](https://github.com/bubbuild/bub/graphs/commit-activity)
[![License](https://img.shields.io/github/license/bubbuild/bub)](LICENSE)

Bub is a **batteries-included, hook-first AI framework**.

Bub is a collaborative agent for shared delivery workflows, evolving into a framework that helps other agents operate with the same collaboration model.
It is not a personal-assistant shell: it is designed for shared environments where work must be inspectable, handoff-friendly, and operationally reliable.

> Documentation: <https://bub.build>

Built on [Republic](https://github.com/bubbuild/republic), Bub treats context as explicit assembly from verifiable interaction history, rather than opaque inherited state.
This aligns with [Socialized Evaluation](https://psiace.me/posts/im-and-socialized-evaluation/): systems are judged by how well teams can inspect, review, and continue work together.

## What Bub Provides

- Multi-operator collaboration in shared delivery environments.
- Explicit command boundaries for predictable execution.
- Verifiable history (`tape`, `anchor`, `handoff`) for audit and continuity.
- Channel-neutral behavior across CLI and message channels.
- Extensible tools and skills with a unified operator-facing workflow.

## Quick Start

```bash
git clone https://github.com/bubbuild/bub.git
cd bub
uv sync
uv run bub run "hello"
uv run bub hooks
uv run bub skills
```

## Skill Layout

```bash
BUB_MODEL=openrouter:qwen/qwen3-coder-next
BUB_API_KEY=your_key_here
```

1. `<workspace>/.agents/skills`
2. `~/.agents/skills`
3. `src/bub_skills/`

```bash
uv run bub
```

## Interaction Model

- `hello`: natural language routed to model.
- `,help`: internal command.
- `,git status`: shell command.
- `, ls -la`: shell command (space after comma is optional).

Common commands:

```text
,help
,tools
,tool.describe name=fs.read
,skills.list
,skills.describe name=friendly-python
,handoff name=phase-1 summary="bootstrap done"
,anchors
,tape.info
,tape.search query=error
,tape.reset archive=true
,quit
```

## Channel Runtime

Telegram:

```bash
BUB_TELEGRAM_TOKEN=123456:token
BUB_TELEGRAM_ALLOW_USERS=123456789,your_username
uv run bub message
```

## Development

```bash
uv run ruff check .
uv run mypy
uv run pytest -q
```
