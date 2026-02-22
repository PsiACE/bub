# Skills

Bub builds on the standard Agent Skills format, then adds a Bub-specific adapter layer.

## Skill Model

A Bub skill has two layers:

1. Standard layer: `SKILL.md` and optional resources
2. Bub layer: optional adapter code for Bub runtime integration

Skills remain valid even without a Bub adapter.

## Minimum Skill

```text
my-skill/
└── SKILL.md
```

## Skill With Bub Adapter

```text
my-skill/
├── SKILL.md
└── agents/
    └── bub/
        ├── plugin.py
        └── agent.yaml
```

## Recommended Layout

```text
my-skill/
├── SKILL.md
├── agents/
│   └── bub/
│       ├── plugin.py
│       └── agent.yaml
├── scripts/
│   └── *.py
└── references/
    └── *.md
```

## Where Bub Discovers Skills

Bub checks skills from:

- project scope
- user scope
- builtin scope

Higher-priority scope overrides lower-priority scope on name collision.

## SKILL.md Frontmatter

Supported fields:

- required: `name`, `description`
- optional: `license`, `compatibility`, `metadata`, `allowed-tools`

## Authoring Guidance

- Keep `SKILL.md` focused and task-oriented
- Move large details to `references/`
- Put deterministic repeatable logic in `scripts/`
- Use clear examples and edge cases for activation quality
