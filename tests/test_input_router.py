"""Tests for the input router."""

from pathlib import Path

from bub.runtime import Runtime


def _make_session(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BUB_HOME", str(tmp_path / "bubhome"))
    monkeypatch.setenv("BUB_MODEL", "openai:gpt-4o-mini")
    monkeypatch.setenv("BUB_API_KEY", "test")
    runtime = Runtime.build(tmp_path)
    return runtime.session


def test_route_internal_command_only(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$tape.info")
    assert result.enter_agent is False
    assert result.agent_input == ""


def test_route_leading_dollar_text(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$hello")
    assert result.enter_agent is True
    assert result.agent_input == "hello"


def test_route_leading_dollar_numeric(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$5")
    assert result.enter_agent is True
    assert result.agent_input == "5"


def test_route_mixed_text_and_command(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("summarize $tape.search query=hello")
    assert result.enter_agent is True
    assert "summarize" in result.agent_input
    assert "<cmd" in result.agent_input


def test_route_unknown_tail_after_internal(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$tape.search query=hello summarize")
    assert result.enter_agent is True
    assert "summarize" in result.agent_input


def test_route_command_error_fallback(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$tape.search")
    assert result.enter_agent is True
    assert "<cmd" in result.agent_input


def test_route_tool_long_flag_value(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$tape.search --query hello")
    assert result.enter_agent is False
    assert result.agent_input == ""


def test_route_tool_runtime_error_fallback(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$fs.read path=missing.txt")
    assert result.enter_agent is True
    assert 'status="error"' in result.agent_input


def test_route_shell_error_message_not_duplicated(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$bash cmd=false")
    assert result.enter_agent is True
    assert "error: exit=1" in result.agent_input
    assert "error: error:" not in result.agent_input


def test_route_dollar_inside_quotes_is_plain_text(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("say '$tape.info'")
    assert result.enter_agent is True
    assert result.agent_input == "say '$tape.info'"
    assert "<cmd" not in result.agent_input


def test_route_escaped_dollar_is_plain_text(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input(r"escaped \$tape.info")
    assert result.enter_agent is True
    assert result.agent_input == r"escaped \$tape.info"
    assert "<cmd" not in result.agent_input


def test_route_multiple_commands_in_one_line(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$tape.info $tape.info")
    assert result.enter_agent is False
    assert result.agent_input == ""
    commands = [entry for entry in session.tape.entries() if entry.kind == "command"]
    assert len(commands) == 2


def test_route_option_terminator_preserves_trailing_text(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$tape.info -- trailing")
    assert result.enter_agent is True
    assert '<cmd name="tape.info" status="ok">' in result.agent_input
    assert "trailing" in result.agent_input


def test_route_bash_allows_literal_option_terminator(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$bash printf '%s' --")
    assert result.enter_agent is False
    assert result.agent_input == ""


def test_route_embedded_bash_cmd_does_not_capture_trailing_text(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("note $bash cmd='echo hi' then summarize")

    assert result.enter_agent is True
    assert '<cmd name="bash" status="ok">' in result.agent_input
    assert "then summarize" in result.agent_input
    assert "hi then summarize" not in result.agent_input

    cmd_end = result.agent_input.index("</cmd>")
    suffix = result.agent_input.index("then summarize")
    assert suffix > cmd_end


def test_route_line_start_bash_keeps_raw_tail_args(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    result = session.handle_input("$bash echo hello")

    assert result.enter_agent is False
    assert result.agent_input == ""
    commands = [entry for entry in session.tape.entries() if entry.kind == "command"]
    assert commands
    latest = commands[-1]
    assert latest.payload.get("name") == "bash"
    assert "hello" in str(latest.payload.get("stdout", ""))


def test_route_assistant_executes_commands(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    route = session.interpret_assistant("note $tape.info")
    assert route.done_requested is False
    assert "<cmd" in route.followup_input
    assert route.visible_text == "note"


def test_route_assistant_done_command(tmp_path, monkeypatch):
    session = _make_session(tmp_path, monkeypatch)
    route = session.interpret_assistant("$done")
    assert route.done_requested is True
