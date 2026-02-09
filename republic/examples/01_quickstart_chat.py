from __future__ import annotations

import os

from republic import LLM


class MissingEnvVarError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Set {name} before running this example.")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingEnvVarError(name)
    return value


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = os.getenv("REPUBLIC_CHAT_MODEL", "openrouter:openrouter/free")

    llm = LLM(model=model, api_key=api_key)
    out = llm.chat("Explain tape-first in one sentence.", max_tokens=48)

    if out.error:
        print("error:", out.error.kind, out.error.message)
        return
    print("text:", out.value)


if __name__ == "__main__":
    main()
