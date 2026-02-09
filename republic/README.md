# Republic

[![Release](https://img.shields.io/github/v/release/psiace/republic)](https://img.shields.io/github/v/release/psiace/republic)
[![Build status](https://img.shields.io/github/actions/workflow/status/psiace/republic/main.yml?branch=main)](https://github.com/psiace/republic/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/psiace/republic/branch/main/graph/badge.svg)](https://codecov.io/gh/psiace/republic)
[![Commit activity](https://img.shields.io/github/commit-activity/m/psiace/republic)](https://img.shields.io/github/commit-activity/m/psiace/republic)
[![License](https://img.shields.io/github/license/psiace/republic)](https://img.shields.io/github/license/psiace/republic)

Build LLM workflows like normal Python while keeping a full audit trail by default.

> Visit https://getrepublic.org for concepts, guides, and API reference.

Republic is a **tape-first** LLM client: messages, tool calls, tool results, errors, and usage are all recorded as structured data. You can make the workflow explicit first, then decide where intelligence should be added.

## Quick Start

```bash
pip install republic
```

```python
from __future__ import annotations

import os

from republic import LLM

api_key = os.getenv("LLM_API_KEY")
if not api_key:
    raise RuntimeError("Set LLM_API_KEY before running this example.")

llm = LLM(model="openrouter:openrouter/free", api_key=api_key)
result = llm.chat("Describe Republic in one sentence.", max_tokens=48)

if result.error:
    print(result.error.kind, result.error.message)
else:
    print(result.value)
```

## Why It Feels Natural

- **Plain Python**: The main flow is regular functions and branches, no extra DSL.
- **Structured Result**: Core interfaces return `StructuredOutput`, with stable `ErrorKind` values.
- **Tools without magic**: Supports both automatic and manual tool execution with clear debugging and auditing.
- **Tape-first memory**: Use anchor/handoff to bound context windows and replay full evidence.
- **Event streaming**: Subscribe to text deltas, tool calls, tool results, usage, and final state.

## Development

```bash
make check
make test
```

See [CONTRIBUTING.md](./CONTRIBUTING.md) for local setup, testing, and release guidance.

## License

[Apache 2.0](./LICENSE)

---

> This project is derived from [lightning-ai/litai](https://github.com/lightning-ai/litai) and inspired by [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai); we hope you like them too.
