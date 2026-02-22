---
name: runtime
description: Stateful runtime orchestration skill. Use when implementing or debugging inbound normalization, session identity, tool routing, state transitions, and failure isolation across multi-turn runtime flows.
---

# Runtime Skill

## Steps

1. Normalize inbound payloads so `content`, `session_id`, and `metadata` are always usable.
2. Resolve session identity deterministically: explicit `session_id` first, then `channel:chat_id`.
3. Set explicit loop boundaries for model and tools: max steps, timeout, and fallback rules.
4. Preserve actionable diagnostics on failures; do not swallow errors.
5. Use `scripts/prepare_context.py` to build stable context payloads.

## Bub Adapter

- Bub adapter entrypoint: `agents/bub/plugin.py`.
- Bub adapter profile: `agents/bub/agent.yaml`.

## Examples

Input example:

```text
Normalize this inbound message and preserve stable session identity.
```

Expected output characteristics:

```text
- deterministic session id
- trimmed content
- metadata includes runtime listener mark
```

## Edge Cases

- If `session_id` is absent but `channel/chat_id` exists, fallback must remain deterministic.
- Empty inbound content should still return a structured result, not an exception.
- Tool-call failures and model failures should be logged distinctly to avoid root-cause confusion.

## References

- See `references/usage.md` for detailed flow and failure-handling guidance.
