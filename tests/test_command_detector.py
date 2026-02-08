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


def test_patch_assignment_text_is_not_detected_as_shell_command() -> None:
    line = 'new_text="def _is_shell_command(line: str) -> bool:\\n    return False"'
    assert detect_line_command(line) is None


def test_very_long_assignment_text_does_not_crash_or_detect_as_command() -> None:
    long_payload = f'new_text="{"a/" * 400}end"'
    assert detect_line_command(long_payload) is None


def test_env_prefixed_shell_command_is_detected() -> None:
    command = detect_line_command("FOO=bar echo hello")
    assert command is not None
    assert command.kind == "shell"
    assert command.name == "echo"
