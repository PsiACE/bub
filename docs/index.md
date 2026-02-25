# Bub

Bub currently implements a minimal hook-first framework:

- The core orchestrates one message turn end-to-end
- Builtin hooks provide default CLI and runtime behavior
- External plugins join the same lifecycle via entry points (`group="bub"`)

## Where To Look

- CLI bootstrap: `src/bub/__main__.py`
- Core runtime orchestration: `src/bub/framework.py`
- Hook specifications: `src/bub/hookspecs.py`
- Hook execution isolation: `src/bub/hook_runtime.py`
- Builtin implementations: `src/bub/builtin/*`
- Skill discovery/validation: `src/bub/skills.py`

## Read Next

- `architecture.md`: lifecycle, hook precedence, and fault isolation
- `cli.md`: `bub run`, `bub hooks`, `bub install`, and comma commands
- `skills.md`: `SKILL.md` frontmatter rules and override behavior
- `features.md`: current capabilities and known boundaries
