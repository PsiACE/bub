# Repository Guidelines

## Project Structure & Module Organization
Core code lives under `src/bub/`:
- `app/`: runtime bootstrap and session wiring
- `core/`: input router, command detection, model runner, agent loop
- `tape/`: append-only tape store, anchor/handoff services
- `tools/`: unified tool registry and progressive tool-view rendering
- `skills/`: skill discovery and loading (`SKILL.md`-based)
- `cli/`: interactive CLI (`bub chat`)
- `channels/`: channel bus/manager and Telegram adapter
- `integrations/`: Republic client setup

Tests are in `tests/`. Documentation is in `docs/`. Legacy implementation is archived in `backup/src_bub_legacy/` (read-only reference).

## Build, Test, and Development Commands
- `uv sync`: install/update dependencies
- `just install`: setup env + hooks
- `uv run bub chat`: run interactive CLI
- `uv run bub message`: run message channels (Telegram/Discord)
- `uv run pytest -q` or `just test`: run tests
- `uv run ruff check .`: lint checks
- `uv run mypy`: static typing checks
- `just check`: lock validation + lint + typing
- `just docs` / `just docs-test`: serve/build docs

## Coding Style & Naming Conventions
- Python 3.12+, 4-space indentation, type hints required for new/modified logic.
- Naming: `snake_case` (functions/variables/modules), `PascalCase` (classes), `UPPER_CASE` (constants).
- Keep functions focused and composable; avoid hidden side effects.
- Format/lint with Ruff (line length: 120). Type-check with mypy.

## Testing Guidelines
- Framework: `pytest`.
- Name files `tests/test_<feature>.py`; name tests by behavior (e.g., `test_user_shell_failure_falls_back_to_model`).
- Cover router semantics, loop stop conditions, tape/anchor behavior, and channel dispatch.
- For behavior changes, update/add tests in the same PR.

## Commit & Pull Request Guidelines
- Follow Conventional Commit style seen in history: `feat:`, `fix:`, `chore:`.
- Keep commits focused; avoid mixing refactor and behavior change without explanation.
- PRs should include:
  - what changed and why
  - impacted paths/modules
  - verification output (`ruff`, `mypy`, `pytest`)
  - docs updates when CLI behavior, commands, or architecture changes

## Security & Configuration Tips
- Use `.env` for secrets (`OPENROUTER_API_KEY`, `BUB_TELEGRAM_TOKEN`); never commit keys.
- Validate Telegram allowlist (`BUB_TELEGRAM_ALLOW_FROM`) before enabling production bots.
