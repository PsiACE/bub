# Text Decisions

`if_` and `classify` are useful when you want model decisions in a clear structured form.

## if_

```python
from republic import LLM

llm = LLM(model="openrouter:openai/gpt-4o-mini", api_key="<API_KEY>")
decision = llm.if_("The release is blocked by a migration failure.", "Should we page on-call now?")

print(decision.value)  # bool | None
print(decision.error)
```

## classify

```python
label = llm.classify(
    "User asks for invoice and tax receipt.",
    ["sales", "support", "finance"],
)

print(label.value)     # one of choices | None
print(label.error)
```

## Usage Tips

- Treat these as shortcut entry points for agentic `if` and classification.
- Keep business logic in regular Python branches for testability and audits.
