# Skills

Bub follows the Agent Skills specification and adds one optional Bub runtime adapter layer.

## Core Contract

Every skill must remain valid as a standard Agent Skill:

```text
my-skill/
└── SKILL.md
```

`SKILL.md` must contain valid YAML frontmatter and body instructions.
The skill directory name must match frontmatter `name`.

## Bub Runtime Extension

If a skill needs Bub runtime hooks, add:

```text
my-skill/
├── SKILL.md
└── agents/
    └── bub/
        ├── adapter.py
        └── agent.yaml
```

- `agents/bub/adapter.py`: optional Bub hook adapter module, exporting `adapter`
- `agents/bub/agent.yaml`: optional prompt/profile data consumed by Bub runtime

This extension is Bub-specific. It does not change standard Agent Skills compatibility.

## Recommended Layout

```text
my-skill/
├── SKILL.md
├── agents/
│   └── bub/
│       ├── adapter.py
│       └── agent.yaml
├── scripts/
│   └── *.py
└── references/
    └── *.md
```

## Discovery And Override

Bub discovers skills from three scopes in priority order:

1. project: `.agent/skills`
2. user: `~/.agent/skills`
3. builtin: `src/bub/skills/builtin`

If names collide, higher-priority scope overrides lower-priority scope.

## Frontmatter Fields

Supported `SKILL.md` frontmatter fields:

- required: `name`, `description`
- optional: `license`, `compatibility`, `metadata`, `allowed-tools`

## Authoring Guidance

- Keep `SKILL.md` concise and activation-oriented
- Move detailed reference material into `references/`
- Put deterministic executable logic into `scripts/`
- Keep Bub-only runtime details inside `agents/bub/`, not in the generic skill contract

## Script Convention

For `scripts/*.py`, prefer standalone `uv` scripts with PEP 723 metadata:

```python
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
```

This keeps execution deterministic and avoids hidden environment assumptions.
