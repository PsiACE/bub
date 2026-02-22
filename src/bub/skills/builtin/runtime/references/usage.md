# Runtime Usage Reference

## Normalization Rules

1. Convert inbound content to trimmed string.
2. Ensure metadata is a dictionary.
3. Add a runtime listener marker when missing.

## Session Rules

1. Use explicit `session_id` when provided.
2. Fallback to `channel:chat_id` when absent.
3. Keep session resolution deterministic across turns.

## Failure Isolation

1. Isolate adapter failures from framework core flow.
2. Emit actionable error details for diagnostics.
3. Keep fallback response behavior deterministic.

## Minimal Test Matrix

1. Message normalization with extra whitespace
2. Session fallback without explicit `session_id`
3. Runtime adapter failure does not break core processing
4. Outbound fallback when no renderer returns output
