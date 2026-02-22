# CLI Usage Reference

## Contract Template

Define every command with:

1. Input parameters and defaults
2. Success output schema
3. Error output schema
4. Exit behavior

## Output Guidance

- Prefer line-oriented output for terminal users.
- If output is consumed by scripts, keep fields stable.
- Avoid mixing diagnostic text with machine-parsable sections.

## Suggested Checks

1. Command registration is deterministic.
2. Help text is explicit for required/optional flags.
3. Failure paths include next-step hints.

## Minimal Test Matrix

1. Successful invocation with default options
2. Successful invocation with explicit options
3. Invalid arguments
4. Runtime dependency unavailable
