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
    tool_model = os.getenv("REPUBLIC_TOOL_MODEL", "openrouter:openai/gpt-4o-mini")
    embedding_model = os.getenv("REPUBLIC_EMBEDDING_MODEL", "openrouter:openai/text-embedding-3-small")

    llm = LLM(model=tool_model, api_key=api_key)

    decision = llm.if_(
        "The checkout API has 30% errors after deployment.",
        "Should we trigger rollback now?",
    )
    print("if:", decision.value, decision.error)

    label = llm.classify(
        "Need VAT invoice and payment receipt.",
        ["sales", "support", "finance"],
    )
    print("classify:", label.value, label.error)

    emb_out = llm.embed(
        ["checkout incident", "rollback decision"],
        model=embedding_model,
    )
    print("embeddings error:", emb_out.error)
    if emb_out.error is None:
        print("embeddings value type:", type(emb_out.value).__name__)


if __name__ == "__main__":
    main()
