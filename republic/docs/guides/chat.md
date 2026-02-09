# Chat

`llm.chat(...)` is the smallest entry point and fits most text-only workloads.

## Prompt Mode

```python
from republic import LLM

llm = LLM(model="openrouter:openrouter/free", api_key="<API_KEY>")
out = llm.chat("Output exactly one word: ready", max_tokens=8)
print(out.value, out.error)
```

## Messages Mode

```python
messages = [
    {"role": "system", "content": "Be concise."},
    {"role": "user", "content": "Explain tape-first in one sentence."},
]
out = llm.chat(messages=messages, max_tokens=48)
```

## Structured Error Handling

```python
result = llm.chat("Write one sentence.")
if result.error:
    if result.error.kind == "temporary":
        print("retry later")
    else:
        print("fail fast:", result.error.message)
```

## Retries and Fallback

```python
llm = LLM(
    model="openai:gpt-4o-mini",
    fallback_models=["anthropic:claude-3-5-sonnet-latest"],
    max_retries=3,
    api_key={"openai": "<OPENAI_KEY>", "anthropic": "<ANTHROPIC_KEY>"},
)

out = llm.chat("Give me one deployment checklist item.")
```

Recommendation: keep `max_retries` small (for example 2-4), and pick fallback models that are slightly more stable while still meeting quality requirements.
