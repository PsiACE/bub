# Republic

Use LLM capabilities like regular Python components, with auditable execution traces by default.

Republic is not a bigger framework. It is a small set of composable primitives:

- `LLM`: One entry point for chat, tools, stream, and embeddings.
- `StructuredOutput`: Key interfaces return `value + error`.
- `Tape`: Append-only records with anchor/handoff/context/query.
- `ToolExecutor`: Tool calls can be automatic or manual.

## 30-Second Preview

```python
from republic import LLM

llm = LLM(model="openrouter:openrouter/free", api_key="<API_KEY>")
out = llm.chat("Explain tape-first in one sentence.", max_tokens=48)

if out.error:
    print(out.error.kind, out.error.message)
else:
    print(out.value)
```

## What You Get

- Smaller API surface with stronger control.
- Visible tool execution paths without hidden magic.
- Run/tape-level behavior tracing for debugging and audits.
- Both text streaming and event streaming for CLI, web, and workers.

---

> This project is derived from [lightning-ai/litai](https://github.com/lightning-ai/litai) and inspired by [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai); we hope you like them too.
