import pytest

from bub.channels.runner import SessionRunner


class DummyChannel:
    output_channel = "dummy"

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.outputs: list[tuple[str, object]] = []

    def is_mentioned(self, _message: object) -> bool:
        return True

    async def get_session_prompt(self, message: object) -> tuple[str, str]:
        assert isinstance(message, str)
        return "session", message

    async def run_prompt(self, session_id: str, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"result:{session_id}"

    async def process_output(self, session_id: str, output: object) -> None:
        self.outputs.append((session_id, output))


@pytest.mark.asyncio
async def test_command_prompt_is_not_buffered() -> None:
    channel = DummyChannel()
    runner = SessionRunner("session", debounce_seconds=1, message_delay_seconds=1, active_time_window_seconds=60)

    await runner.process_message(channel, ",help")

    assert channel.prompts == [",help"]
    assert channel.outputs == [("session", "result:session")]
    assert runner._prompts == []
    assert runner._running_task is None
