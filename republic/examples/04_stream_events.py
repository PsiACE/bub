from __future__ import annotations

import os

from republic import LLM, tool


class MissingEnvVarError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Set {name} before running this example.")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingEnvVarError(name)
    return value


@tool
def lookup_status(service: str) -> str:
    return f"{service}=healthy"


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = os.getenv("REPUBLIC_STREAM_MODEL", "openrouter:openai/gpt-4o-mini")
    llm = LLM(model=model, api_key=api_key)

    print("== stream text ==")
    stream = llm.stream("Give me three short words.", max_tokens=16)
    text = "".join(chunk for chunk in stream)
    print("text:", text)
    print("error:", stream.error)
    print("usage:", stream.usage)

    print("== stream events ==")
    events = llm.stream_events(
        "Summarize current health and use lookup_status for auth-service.",
        tools=[lookup_status],
        max_tokens=128,
    )
    for event in events:
        if event.kind == "text":
            print(event.data["delta"], end="")
        elif event.kind == "tool_call":
            print("\ntool_call:", event.data)
        elif event.kind == "tool_result":
            print("\ntool_result:", event.data)
        elif event.kind == "usage":
            print("\nusage:", event.data)
        elif event.kind == "final":
            print("\nfinal:", event.data)


if __name__ == "__main__":
    main()
