from pathlib import Path

from bub.cli.interactive import InteractiveCli


class _DummyRuntime:
    def __init__(self) -> None:
        self.workspace = Path.cwd()
        self.registry = type("_Registry", (), {"descriptors": staticmethod(lambda: [])})()

        class _Settings:
            model = "openrouter:test"

            @staticmethod
            def resolve_home() -> Path:
                return Path.cwd()

        self.settings = _Settings()

    def get_session(self, _session_id: str):
        class _Tape:
            @staticmethod
            def info():
                class _Info:
                    entries = 0
                    anchors = 0
                    last_anchor = None

                return _Info()

        class _Session:
            tape = _Tape()

        return _Session()


def test_normalize_input_keeps_agent_mode_text() -> None:
    cli = InteractiveCli(_DummyRuntime())  # type: ignore[arg-type]
    cli._mode = "agent"
    assert cli._normalize_input("echo hi") == "echo hi"


def test_normalize_input_adds_shell_prefix_in_shell_mode() -> None:
    cli = InteractiveCli(_DummyRuntime())  # type: ignore[arg-type]
    cli._mode = "shell"
    assert cli._normalize_input("echo hi") == ", echo hi"


def test_normalize_input_keeps_explicit_prefixes_in_shell_mode() -> None:
    cli = InteractiveCli(_DummyRuntime())  # type: ignore[arg-type]
    cli._mode = "shell"
    assert cli._normalize_input(",help") == ",help"
    assert cli._normalize_input(",ls -la") == ",ls -la"
    assert cli._normalize_input(", ls -la") == ", ls -la"
