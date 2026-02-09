# Embeddings

The embedding interface shares the same `LLM` facade as chat.

```python
from republic import LLM

llm = LLM(model="openrouter:openai/text-embedding-3-small", api_key="<API_KEY>")
out = llm.embed(["republic", "tape-first"])

if out.error:
    print(out.error.kind, out.error.message)
else:
    print(out.value)
```

You can also override the model per call:

```python
out = llm.embed(
    "incident root cause analysis",
    model="openrouter:openai/text-embedding-3-small",
)
```
