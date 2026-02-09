# Tools

Tool workflows have two paths:

- Automatic execution: `llm.run_tools(...)`
- Manual execution: `llm.tool_calls(...)` + `llm.tools.execute(...)`

## Define a Tool

```python
from republic import tool

@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny"
```

## Automatic Execution (Faster)

```python
from republic import LLM

llm = LLM(model="openrouter:openai/gpt-4o-mini", api_key="<API_KEY>")
out = llm.run_tools("What is weather in Tokyo?", tools=[get_weather])

print(out.kind)         # text | tools | error
print(out.tool_results)
print(out.error)
```

## Manual Execution (More Control)

```python
calls = llm.tool_calls("Use get_weather for Berlin.", tools=[get_weather])
if calls.error:
    raise RuntimeError(calls.error.message)

execution = llm.tools.execute(calls.value, tools=[get_weather])
print(execution.tool_results)
print(execution.error)
```

## Tools with Context

When a tool needs tape/run metadata, declare `context=True`.

```python
from republic import ToolContext, tool

@tool(context=True)
def save_ticket(title: str, context: ToolContext) -> dict[str, str]:
    return {
        "title": title,
        "run_id": context.run_id,
        "tape": context.tape or "none",
    }
```
