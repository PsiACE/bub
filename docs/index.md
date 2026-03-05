# Bub

Bub is a hook-first AI framework built on top of `pluggy`.

- `BubFramework` runs one inbound message through a deterministic turn pipeline.
- Builtin plugin `bub.builtin.hook_impl` provides default CLI, runtime, and channel behavior.
- External plugins join the same lifecycle via Python entry points (`group="bub"`).

## Code Entry Points

- CLI bootstrap: `src/bub/__main__.py`
- Runtime orchestration: `src/bub/framework.py`
- Hook contracts: `src/bub/hookspecs.py`
- Hook dispatcher runtime: `src/bub/hook_runtime.py`
- Builtin implementations: `src/bub/builtin/*`
- Skill discovery: `src/bub/skills.py`

## Read Next

- `architecture.md`: real execution flow, precedence, and error semantics
- `extension-guide.md`: how to build and publish hook-based extensions
- `cli.md`: `bub run/hooks/message/chat` usage
- `channels.md`: builtin channels and session behavior
- `skills.md`: `SKILL.md` discovery and override rules
- `features.md`: capabilities and current boundaries
