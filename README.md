# Bub

Bub it. Build it.

Bub is a **batteries-included, hook-first AI framework**.

The framework keeps only a minimal core and moves behavior into skills:

- model execution and tool loop
- command routing and runtime tape behavior
- input listener hooks (normalize + session resolution) in the same runtime process
- CLI command registration
- channel/bus behaviors provided by project skills

Built-in batteries in this baseline:

- `cli`
- `runtime` (Republic-driven runtime battery with routing, tools, and tape-backed sessions)

## Runtime Defaults

- Without usable Republic model credentials, the framework still runs and returns prompt text as output.
- `runtime` can be controlled with environment variables:
  - `BUB_RUNTIME_ENABLED=1|0|auto`
  - `BUB_MODEL`, `BUB_API_KEY`, `BUB_API_BASE`
  - `BUB_RUNTIME_MAX_STEPS`, `BUB_RUNTIME_MAX_TOKENS`, `BUB_RUNTIME_MODEL_TIMEOUT_SECONDS`

## Design Goal

`input` is treated as a message bus concern, not a fixed CLI feature.
The core only coordinates one turn through hook contracts.
Everything else is skill-driven.
`message` is user-defined and can be mapping-based or object-based.

## Quick Start

```bash
uv sync
uv run bub run "hello"
uv run bub hooks
uv run bub skills
BUB_RUNTIME_ENABLED=1 uv run bub run ",help"
```

## Skill Layout

Skills are discovered from:

1. `<workspace>/.agent/skills`
2. `~/.agent/skills`
3. `src/bub/skills/builtin`

## Run Tests

```bash
uv run ruff check .
uv run mypy
uv run pytest -q
```
