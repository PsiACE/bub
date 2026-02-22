# Architecture

Bub uses a minimal-kernel architecture: the core orchestrates a turn, while skills provide behavior.

## Principles

- Keep core responsibilities small and stable
- Put runtime behavior behind explicit extension points
- Preserve predictable override semantics
- Prefer graceful degradation over global failure

## Guarantees

### Deterministic Turn Lifecycle

Each inbound message follows a stable lifecycle:

1. normalize input
2. resolve session
3. load context/state
4. build model input
5. run model/tools
6. persist state
7. render outbound messages
8. dispatch output

### Deterministic Skill Resolution

Skills are resolved by scope priority:

1. project scope
2. user scope
3. builtin scope

If names collide, higher-priority scope wins.

### Failure Isolation

- Skill load failures are isolated
- Hook execution failures are isolated per extension
- The framework keeps the turn loop operational with safe fallbacks

## Non-goals

- Enforcing one global business schema for all messages
- Hardcoding domain behavior into the kernel
- Merging duplicate skill names across scopes

## See Also

- `docs/skills.md` for skill contract and layout
- `docs/cli.md` for command behavior
