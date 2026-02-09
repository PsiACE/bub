# Tape

Tape is an append-only execution log and a context selector.

## Core Actions

- `handoff(name, state=...)`: Create a new task anchor.
- `chat(...)`: Continue on the current tape and record the run.
- `entries()`: Inspect full entries (message/tool/error/event).
- `query()`: Run slice queries.

## Minimal Session

```python
from republic import LLM

llm = LLM(model="openrouter:openrouter/free", api_key="<API_KEY>")
tape = llm.tape("ops")

tape.handoff("incident_42", state={"owner": "tier1"})
out = tape.chat("Connection pool is exhausted. Give triage steps.", max_tokens=96)

print(out.value)
print([entry.kind for entry in tape.read_entries()])
```

## Anchor-Based Context Slicing

```python
tape.handoff("incident_43")
_ = tape.chat("This time the issue is cache penetration.")

previous = tape.query().after_anchor("incident_42").all()
print([entry.kind for entry in previous.entries])
```

## Conventions

- Tape entries are append-only and never overwrite history.
- Query/Context depend on entry order, not external indexes.
- Errors are recorded as first-class entries for replay.
