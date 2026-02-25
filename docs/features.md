# Key Features

## Framework Core

- Hook-first architecture with `pluggy`
- Deterministic turn lifecycle in `BubFramework.process_inbound()`
- Safe fallbacks for missing bus, missing model output, and missing outbound renderers
- Per-hook-implementation fault isolation via `HookRuntime`

## Skills

- `SKILL.md` frontmatter validation (`name`, `description`, optional fields)
- Deterministic discovery/override order: project -> global -> builtin
- Skill body loading for runtime commands like `,skills.describe`

## Runtime

- Builtin CLI commands: `run`, `hooks`, `install`
- Builtin runtime engine with:
  - LLM turn execution through Republic tools
  - Internal comma command mode (`help`, `tools`, `fs.*`, `tape.*`, `skills.*`)
  - Shell fallback for unknown comma commands
- Runtime event logging to `.bub/runtime/*.jsonl`

## Plugin Extensibility

- External plugins loaded from Python entry points (`group="bub"`)
- First-result hooks for override-style behavior
- Broadcast hooks for multi-observer side effects (`save_state`, `dispatch_outbound`, `on_error`)

## Current Boundaries

- No strict envelope schema: `Envelope` is `Any`
- No enforced global persistence/state format across plugins
- Repository currently ships the `src/bub_skills` root, but no mandatory builtin skill pack behavior in core
