# Bub

Bub it. Build it.

Bub is a batteries-included, skill-first AI framework with a minimal core and skill-owned behavior.

## Why Bub

Bub keeps the framework kernel small and stable, and moves runtime capabilities into skills.
This makes behavior easy to evolve without forking the core.

## Design Principles

- Minimal kernel for orchestration and safety boundaries
- Skill-first extension model for runtime behavior
- Standard Agent Skills contract first, Bub runtime adapter second
- Standards-based skill metadata (`SKILL.md`)
- Predictable override order across project, user, and builtin scopes

## Builtin Batteries

- `cli`: command entrypoints and diagnostics
- `runtime`: message handling, model/tool execution, and outbound rendering

## Quick Start

```bash
uv sync
uv run bub run "hello"
uv run bub hooks
uv run bub skills
BUB_RUNTIME_ENABLED=1 uv run bub run ",help"
```

## Documentation

- `docs/index.md`: overview
- `docs/features.md`: capability summary
- `docs/architecture.md`: architecture principles and guarantees
- `docs/skills.md`: skill authoring and extension model
- `docs/cli.md`: command usage

## Development Checks

```bash
uv run ruff check .
uv run mypy
uv run pytest -q
```
