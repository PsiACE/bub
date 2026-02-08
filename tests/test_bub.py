"""Tests for Bub."""

import json
from pathlib import Path

from bub.agent import Context
from bub.config import get_settings
from bub.tools import build_agent_tools


class TestSettings:
    """Test settings configuration."""

    def test_settings_with_model(self, monkeypatch):
        """Test settings with model configuration."""
        monkeypatch.setenv("BUB_MODEL", "openai:gpt-4o-mini")
        settings = get_settings()
        assert settings.model == "openai:gpt-4o-mini"

    def test_settings_with_agents_md(self, tmp_path, monkeypatch):
        """Test settings with AGENTS.md override."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("System prompt from AGENTS.md")
        settings = get_settings(tmp_path)
        assert settings.system_prompt is not None
        assert settings.system_prompt.startswith("System prompt from AGENTS.md")
        assert "<available_skills>" in settings.system_prompt

    def test_settings_with_skills_section(self, tmp_path, monkeypatch):
        """Test settings include available skills metadata."""
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        skill_dir = tmp_path / ".agent" / "skills" / "code_review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            ("---\nname: code-review\ndescription: Run review checks.\n---\n\nSkill instructions.\n"),
            encoding="utf-8",
        )

        settings = get_settings(tmp_path)
        assert settings.system_prompt is not None
        assert "<available_skills>" in settings.system_prompt
        assert "<name>code-review</name>" in settings.system_prompt
        assert "code_review/SKILL.md" in settings.system_prompt


class TestTools:
    """Test tool implementations."""

    def _tool_map(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("BUB_HOME", str(tmp_path / "bubhome"))
        context = Context(workspace_path=tmp_path)
        tools = build_agent_tools(context)
        return {tool.name: tool for tool in tools}

    def test_default_tool_names(self, tmp_path, monkeypatch):
        """Test default tool names."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        assert set(tool_map.keys()) == {
            "bash",
            "fs_edit",
            "fs_glob",
            "fs_grep",
            "fs_read",
            "fs_write",
            "handoff",
            "help",
            "status",
            "tape_anchors",
            "tape_info",
            "tape_reset",
            "tape_search",
            "tools",
            "web_fetch",
            "web_search",
        }

    def test_write_and_read(self, tmp_path, monkeypatch):
        """Test write then read tool."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        result = tool_map["fs_write"].run(path="test.txt", content="line1\nline2\nline3\n")
        assert result == "ok"

        read_result = tool_map["fs_read"].run(path="test.txt", offset=1, limit=1)
        assert "2| line2" in read_result

    def test_edit_tool(self, tmp_path, monkeypatch):
        """Test edit tool replacement."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        tool_map["fs_write"].run(path="edit.txt", content="hello world")

        result = tool_map["fs_edit"].run(path="edit.txt", old="world", new="bub")
        assert result == "ok"
        assert (tmp_path / "edit.txt").read_text() == "hello bub"

    def test_edit_requires_unique(self, tmp_path, monkeypatch):
        """Test edit tool requires unique match unless all=true."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        tool_map["fs_write"].run(path="dup.txt", content="a a a")

        result = tool_map["fs_edit"].run(path="dup.txt", old="a", new="b")
        assert result.startswith("error: old_string appears")

    def test_glob_tool(self, tmp_path, monkeypatch):
        """Test glob tool."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        (tmp_path / "a.txt").write_text("one")
        (tmp_path / "b.md").write_text("two")

        result = tool_map["fs_glob"].run(path=".", pattern="*.txt")
        assert "a.txt" in result

    def test_grep_tool(self, tmp_path, monkeypatch):
        """Test grep tool."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        (tmp_path / "hello.txt").write_text("hello\nworld\n")

        result = tool_map["fs_grep"].run(pattern="hello", path=".")
        assert "hello.txt:1:hello" in result

    def test_bash_tool(self, tmp_path, monkeypatch):
        """Test bash tool."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        result = tool_map["bash"].run(cmd="echo 'Hello, World!'")
        assert "Hello, World!" in result

    def test_bash_tool_error(self, tmp_path, monkeypatch):
        """Test bash tool non-zero exit handling."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        result = tool_map["bash"].run(cmd="false")
        assert result.startswith("error: exit=1")

    def test_web_fetch_tool(self, tmp_path, monkeypatch):
        """Test web_fetch tool converts HTML to markdown."""
        tool_map = self._tool_map(tmp_path, monkeypatch)
        observed_urls: list[str] = []

        class _Headers:
            def get_content_charset(self):
                return "utf-8"

        class _Response:
            headers = _Headers()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                _ = (exc_type, exc, tb)
                return False

            def read(self, size: int | None = None) -> bytes:
                body = b"<html><body><h1>Title</h1><p>Hello world.</p></body></html>"
                return body if size is None else body[:size]

        def _fake_urlopen(request, timeout=0):
            _ = timeout
            observed_urls.append(request.full_url)
            return _Response()

        monkeypatch.setattr("bub.tools.factories.web.urllib_request.urlopen", _fake_urlopen)
        result = tool_map["web_fetch"].run(url="example.com")
        assert observed_urls == ["https://example.com"]
        assert "Title" in result
        assert "Hello world." in result

    def test_web_search_tool(self, tmp_path, monkeypatch):
        """Test web_search tool calls Ollama API and formats results."""
        monkeypatch.setenv("BUB_OLLAMA_API_KEY", "ollama-test-key")
        monkeypatch.setenv("BUB_OLLAMA_API_BASE", "https://search.ollama.test/api")
        tool_map = self._tool_map(tmp_path, monkeypatch)
        observed_request: dict[str, str] = {}

        class _Headers:
            def get_content_charset(self):
                return "utf-8"

        class _Response:
            headers = _Headers()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                _ = (exc_type, exc, tb)
                return False

            def read(self, size: int | None = None) -> bytes:
                _ = size
                payload = {
                    "results": [
                        {
                            "title": "Example",
                            "url": "https://example.com",
                            "content": "Example snippet",
                        }
                    ]
                }
                return json.dumps(payload).encode("utf-8")

        def _fake_urlopen(request, timeout=0):
            _ = timeout
            observed_request["url"] = request.full_url
            observed_request["auth"] = request.headers.get("Authorization", "")
            observed_request["payload"] = request.data.decode("utf-8") if request.data else ""
            return _Response()

        monkeypatch.setattr("bub.tools.factories.web.urllib_request.urlopen", _fake_urlopen)
        result = tool_map["web_search"].run(query="test query", max_results=3)

        assert observed_request["url"] == "https://search.ollama.test/api/web_search"
        assert observed_request["auth"] == "Bearer ollama-test-key"
        assert json.loads(observed_request["payload"]) == {"query": "test query", "max_results": 3}
        assert "Example" in result
        assert "https://example.com" in result
        assert "Example snippet" in result
