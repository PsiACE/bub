# Quickstart

## Install

```bash
pip install republic
```

## Step 1: Create an LLM

Republic uses the `provider:model` format.

```python
from republic import LLM

llm = LLM(model="openrouter:openrouter/free", api_key="<API_KEY>")
```

## Step 2: Send one request

```python
out = llm.chat("Write one short release note.", max_tokens=48)

if out.error:
    print("error:", out.error.kind, out.error.message)
else:
    print("text:", out.value)
```

## Step 3: Add an auditable trace to the session

`tape` organizes context around anchors by default, so start with one `handoff`.

```python
tape = llm.tape("release-notes")
tape.handoff("draft_v1", state={"owner": "assistant"})

reply = tape.chat("Summarize the version changes in three bullets.", system_prompt="Keep it concise.")
print(reply.value)
```

## Step 4: Handle failures and fallback

```python
llm = LLM(
    model="openai:gpt-4o-mini",
    fallback_models=["openrouter:openrouter/free"],
    max_retries=2,
    api_key={"openai": "<OPENAI_KEY>", "openrouter": "<OPENROUTER_KEY>"},
)

result = llm.chat("say hello", max_tokens=8)
if result.error:
    # error.kind is one of invalid_input/config/provider/tool/temporary/not_found/unknown
    print(result.error.kind, result.error.message)
```
