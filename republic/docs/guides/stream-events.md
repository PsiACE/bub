# Stream Events

Republic provides two streaming modes:

- `stream(...)`: text deltas only.
- `stream_events(...)`: full events including text, tools, usage, and final.

## Text Stream

```python
from republic import LLM

llm = LLM(model="openrouter:openai/gpt-4o-mini", api_key="<API_KEY>")
stream = llm.stream("Give me three words.")
text = "".join(chunk for chunk in stream)

print(text)
print(stream.error)
print(stream.usage)
```

## Event Stream

```python
events = llm.stream_events(
    "Plan deployment and call a tool if needed.",
    tools=[],
)

for event in events:
    if event.kind == "text":
        print(event.data["delta"], end="")
    elif event.kind == "tool_call":
        print("\ncall=", event.data)
    elif event.kind == "tool_result":
        print("\nresult=", event.data)
    elif event.kind == "usage":
        print("\nusage=", event.data)
    elif event.kind == "final":
        print("\nfinal=", event.data)
```

The `final` event contains `text/tool_calls/tool_results/usage/ok`, which is a good fit for final UI state or audit persistence.
