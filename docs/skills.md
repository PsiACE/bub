# Skills

Bub treats skills as discoverable `SKILL.md` documents with validated frontmatter.

## Minimal Contract

Each skill directory must contain a `SKILL.md` file:

```text
my-skill/
`-- SKILL.md
```

Validation rules from `src/bub/skills.py`:

- `SKILL.md` must start with YAML frontmatter (`--- ... ---`)
- frontmatter must include non-empty `name` and `description`
- directory name must exactly match frontmatter `name`
- `name` must match regex `^[a-z0-9]+(?:-[a-z0-9]+)*$`
- if provided, `metadata` must be a map of `string -> string`

## Frontmatter Fields

Currently enforced fields:

- required: `name`, `description`
- optional with type check: `metadata`

Other extra keys are allowed but not validated by core.

## Discovery And Override

Skills are discovered from three roots in this precedence order:

1. project: `.agents/skills`
2. user: `~/.agents/skills`
3. builtin: `src/bub_skills`

If names collide, earlier roots in this list win.

## Runtime Access

Builtin command mode can inspect discovered skills:

```bash
uv run bub run ",skills.list"
uv run bub run ",skills.describe name=my-skill"
```

If no valid skills are discovered, `,skills.list` returns `(no skills)`.

## Authoring Guidance

- keep `SKILL.md` concise and action-oriented
- keep metadata small and deterministic
- use lowercase kebab-case names for compatibility

## Optional Script Convention

For `scripts/*.py`, a practical standalone convention is PEP 723 with `uv`:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
```
