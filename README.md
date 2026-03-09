# Bub

[Bub](https://github.com/bubbuild/bub) is a common shape for agents.

It starts from a simple question: if there are many agents in the world, what kind of agent is a Bub?

A Bub is an agent that can live inside shared operator environments with explicit boundaries, visible execution evidence, and safe handoff.

The point is not only to complete tasks, but to remain understandable, reviewable, and continuable when more humans and agents join the work.

## Current Implementation

This repository is the current Python implementation of Bub.
It is hook-first, built on `pluggy`, and keeps the core small while builtins and plugins provide behavior.
In this implementation, Bub uses [Republic](https://github.com/bubbuild/republic) as its context runtime and [constructs context from tape](https://tape.systems).

- CLI bootstrap: `src/bub/__main__.py` (Typer app)
- Turn orchestrator: `src/bub/framework.py`
- Hook contract: `src/bub/hookspecs.py`
- Builtin hooks/runtime: `src/bub/builtin/hook_impl.py` + `src/bub/builtin/engine.py`
- Skill discovery and validation: `src/bub/skills.py`

## Quick Start

```bash
git clone https://github.com/bubbuild/bub.git
cd bub
uv sync
uv run bub --help
```

```bash
# Runtime off: falls back to model_output=prompt
BUB_RUNTIME_ENABLED=0 uv run bub run "hello"
```

```bash
# Internal command mode (line starts with ',')
BUB_RUNTIME_ENABLED=0 uv run bub run ",help"
```

```bash
# Model runtime (hosted providers usually require a key)
BUB_API_KEY=your_key uv run bub run "Summarize this repository"
```

```bash
# OpenAI Codex OAuth (no provider API key required)
uv run bub auth login openai
BUB_MODEL=openai:gpt-5-codex uv run bub chat
```

## CLI Commands

- `bub run MESSAGE`: execute one inbound turn and print outbound messages
- `bub auth login openai`: persist OpenAI Codex OAuth credentials for later runs
- `bub hooks`: print hook-to-plugin bindings
- `bub install PLUGIN_SPEC`: install plugin from PyPI or `owner/repo` (GitHub shorthand)

## Runtime Behavior

- Regular text input: uses `run_model`; if runtime is unavailable, output falls back to the prompt text
- Comma commands: `,help`, `,tools`, `,fs.read ...`, etc.
- Unknown comma commands: executed as `bash -lc` in workspace
- Session event log: `.bub/runtime/<session-hash>.jsonl`
- `AGENTS.md`: if present in workspace, appended to runtime system prompt

## Skills

- Discovery roots with deterministic override:
  1. `<workspace>/.agent/skills`
  2. `~/.agent/skills`
  3. `src/bub_skills`
- Each skill directory must include `SKILL.md`
- Supported frontmatter fields:
  - required: `name`, `description`
  - optional: `license`, `compatibility`, `metadata`, `allowed-tools`

## Plugin Development

Plugins are loaded from Python entry points in `group="bub"`:

```toml
[project.entry-points."bub"]
my_plugin = "my_package.my_plugin"
```

Implement hooks with `@hookimpl` following `BubHookSpecs`.

## Runtime Environment Variables

- `BUB_RUNTIME_ENABLED`: `auto` (default), `1`, `0`
- `BUB_MODEL`: default `openrouter:qwen/qwen3-coder-next`
- `BUB_API_KEY`: runtime provider key; optional when using `openai:*` models with `bub auth login openai`
- `BUB_API_BASE`: optional provider base URL
- `BUB_RUNTIME_MAX_STEPS`: default `8`
- `BUB_RUNTIME_MAX_TOKENS`: default `1024`
- `BUB_RUNTIME_MODEL_TIMEOUT_SECONDS`: default `90`

## Documentation

- `docs/index.md`: overview
- `docs/architecture.md`: lifecycle, precedence, and failure isolation
- `docs/skills.md`: skill discovery and frontmatter constraints
- `docs/cli.md`: CLI usage and comma command mode
- `docs/features.md`: implemented capabilities and limits

## Development Checks

```bash
uv run ruff check .
uv run mypy src
uv run pytest -q
```

## License

[Apache-2.0](./LICENSE)
