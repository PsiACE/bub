# Architecture

## Framework Kernel

- `BubFramework`
- `BubHookSpecs`
- `Skill Loader`

The kernel only coordinates a turn. It does not own channel, model, or tool behavior.
Those concerns are provided by skills through hooks.

The framework is batteries-included: default skills provide a runnable baseline,
while every battery can be overridden by project or global skills.

Current builtin baseline:

- `cli` skill: registers `run`, `skills`, and `hooks` commands
- `runtime` skill: input listener hooks, model runtime, tool loop, command-compatible routing

## Hook Pipeline

1. `normalize_inbound`
2. `resolve_session`
3. `load_state`
4. `build_prompt`
5. `run_model`
6. `save_state`
7. `render_outbound`
8. `dispatch_outbound`

## Extension Ownership

- `cli` commands are registered by `register_cli_commands`.
- `bus` instances are provided by `provide_bus`.
- `message` shape is defined by users and adapted by skills.

## Runtime Safety

- Skill load failures are isolated and tracked in `failed_skills`.
- Hook runtime failures are isolated per plugin and reported via `on_error`.
- If no model skill returns output, the framework falls back to the prompt text to keep the process alive.

## Skill Resolution

1. workspace `.agent/skills`
2. user `~/.agent/skills`
3. builtin skills

If two skills share the same name, higher precedence source wins.
At runtime, project skills execute before global and builtin implementations.
