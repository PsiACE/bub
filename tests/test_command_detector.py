from bub.core.command_detector import detect_line_command


def test_detect_internal_command() -> None:
    command = detect_line_command(",help")
    assert command is not None
    assert command.kind == "internal"
    assert command.name == "help"


def test_detect_shell_command() -> None:
    command = detect_line_command("echo hello")
    assert command is not None
    assert command.kind == "shell"
    assert command.name == "echo"


def test_non_command_text_returns_none() -> None:
    assert detect_line_command("请帮我总结今天的改动") is None
