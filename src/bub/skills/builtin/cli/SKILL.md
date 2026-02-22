---
name: cli
description: Command-surface design and diagnostics skill. Use when defining CLI command contracts, arguments, output formats, observability commands, or reviewing and extending existing CLI behavior.
---

# CLI Core Skill

## Steps

1. Define a clear command contract: inputs, defaults, output shape, and failure semantics.
2. Prioritize diagnostics commands first (status, config, hooks, failure summaries), then business commands.
3. Use `scripts/command_index.py` to generate deterministic command listings.
4. Add minimal tests for each new command: one success path and at least one failure path.

## Examples

Input example:

```text
Please add a new `bub doctor` command that validates runtime dependencies.
```

Expected output characteristics:

```text
- command contract is explicit
- diagnostics output is machine-parsable
- failures provide actionable hints
```

## Edge Cases

- Keep output both human-readable and script-parseable; avoid mixed ambiguous formats.
- If command names conflict, identify the conflict source before proposing alternatives.
- When default values affect compatibility, document the impact explicitly.

## Bub Adapter

- Bub adapter entrypoint: `agents/bub/plugin.py`.
- Bub adapter profile: `agents/bub/agent.yaml`.

## References

- See `references/usage.md` for detailed constraints and templates.
