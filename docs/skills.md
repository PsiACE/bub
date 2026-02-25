# Skills

Bub currently treats skills as discoverable `SKILL.md` documents with validated frontmatter.

## Minimal Contract

Each skill directory must contain a `SKILL.md` file:

```text
my-skill/
`-- SKILL.md
```

Rules enforced by `src/bub/skills.py`:

- `SKILL.md` must start with YAML frontmatter (`--- ... ---`)
- Frontmatter must include non-empty `name` and `description`
- Directory name must exactly match frontmatter `name`
- `name` must match regex: `^[a-z0-9]+(?:-[a-z0-9]+)*$`

## Supported Frontmatter Fields

- Required:
  - `name` (string)
  - `description` (string)
- Optional:
  - `license` (string)
  - `compatibility` (string)
  - `metadata` (map of `string -> string`)
  - `allowed-tools` (string)

## Discovery And Override

Bub discovers skills from three scopes in priority order:

1. project: `.agent/skills`
2. user: `~/.agent/skills`
3. builtin: `src/bub_skills`

If names collide, higher-priority scope overrides lower-priority scope.

## Runtime Access To Skills

Builtin runtime command mode can inspect discovered skills:

```bash
BUB_RUNTIME_ENABLED=0 uv run bub run ",skills.list"
BUB_RUNTIME_ENABLED=0 uv run bub run ",skills.describe name=my-skill"
```

If no valid skills are discovered, `,skills.list` returns `(no skills)`.

## Authoring Guidance

- Keep `SKILL.md` concise and action-oriented
- Keep metadata strict and minimal to avoid discovery failures
- Use lowercase kebab-case names to satisfy validation

## Optional Script Convention

For `scripts/*.py`, a practical standalone convention is PEP 723 with `uv`:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
```

This keeps execution deterministic and reduces hidden environment assumptions.
