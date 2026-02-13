# Bub

Bub it. Build it.

Bub is a **batteries-included, hook-first AI framework**.

The framework keeps only a minimal core and moves behavior into skills:

- message normalization and session mapping
- state and memory logic
- model execution
- outbound rendering and dispatch
- CLI command registration
- bus provisioning

Built-in batteries in this baseline:

- `input-bus`
- `memory-tape`
- `model-echo`
- `output-stdout`
- `cli-core`

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
