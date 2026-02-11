from pathlib import Path

from bub.integrations.republic_client import MAX_AGENTS_PROMPT_CHARS, read_workspace_agents_prompt


def test_read_workspace_agents_prompt_returns_empty_for_missing_file(tmp_path: Path) -> None:
    assert read_workspace_agents_prompt(tmp_path) == ""


def test_read_workspace_agents_prompt_returns_full_content_when_small(tmp_path: Path) -> None:
    content = "name: test\nbody"
    (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")
    assert read_workspace_agents_prompt(tmp_path) == content


def test_read_workspace_agents_prompt_truncates_when_too_large(tmp_path: Path) -> None:
    content = "A" * (MAX_AGENTS_PROMPT_CHARS + 123)
    (tmp_path / "AGENTS.md").write_text(content, encoding="utf-8")

    prompt = read_workspace_agents_prompt(tmp_path)
    assert "AGENTS.md truncated" in prompt
    assert len(prompt) < len(content)
    assert prompt.startswith("A")
    assert prompt.endswith("A")
