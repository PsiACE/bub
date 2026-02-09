from __future__ import annotations

import os

from pydantic import BaseModel

from republic import LLM, ToolContext, tool, tool_from_model


class MissingEnvVarError(RuntimeError):
    def __init__(self, name: str) -> None:
        super().__init__(f"Set {name} before running this example.")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise MissingEnvVarError(name)
    return value


@tool
def get_weather(city: str) -> str:
    return f"{city}: sunny"


@tool(context=True)
def save_note(title: str, context: ToolContext) -> dict[str, str]:
    return {
        "title": title,
        "run_id": context.run_id,
        "tape": context.tape or "none",
    }


class Ticket(BaseModel):
    title: str
    severity: str


def create_ticket(payload: Ticket) -> dict[str, str]:
    return payload.model_dump()


def main() -> None:
    api_key = require_env("LLM_API_KEY")
    model = os.getenv("REPUBLIC_TOOL_MODEL", "openrouter:openai/gpt-4o-mini")
    llm = LLM(model=model, api_key=api_key)

    print("== auto tools ==")
    auto = llm.run_tools("Use get_weather for Tokyo.", tools=[get_weather])
    print(auto.kind, auto.tool_results, auto.error)

    print("== manual tools ==")
    calls = llm.tool_calls("Use get_weather for Berlin.", tools=[get_weather])
    if calls.error:
        print("tool call error:", calls.error)
        return
    manual = llm.tools.execute(calls.value, tools=[get_weather])
    print(manual.tool_results, manual.error)

    print("== pydantic tool ==")
    ticket_tool = tool_from_model(Ticket, create_ticket)
    ticket_calls = llm.tool_calls(
        "Create a ticket with title 'db timeout' and severity 'high'.",
        tools=[ticket_tool],
    )
    if ticket_calls.error:
        print("ticket error:", ticket_calls.error)
        return
    ticket_exec = llm.tools.execute(ticket_calls.value, tools=[ticket_tool])
    print(ticket_exec.tool_results, ticket_exec.error)

    print("== context tool with tape ==")
    tape = llm.tape("ops-tools")
    tape.handoff("incident", state={"owner": "tier1"})
    from_tape = tape.run_tools("Call save_note with title 'restart database'.", tools=[save_note])
    print(from_tape.kind, from_tape.tool_results, from_tape.error)


if __name__ == "__main__":
    main()
