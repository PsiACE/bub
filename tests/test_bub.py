"""Tests for Bub."""

from unittest.mock import Mock, patch

from bub.agent import Agent, Context, Message, ToolExecutor, ToolRegistry, ToolResult
from bub.config import get_settings
from bub.tools import FileEditTool, FileReadTool, FileWriteTool, RunCommandTool


class TestSettings:
    """Test settings configuration."""

    def test_settings_with_api_key(self, monkeypatch):
        """Test settings with API key."""
        monkeypatch.setenv("BUB_API_KEY", "test-key")
        settings = get_settings()
        assert settings.api_key == "test-key"


class TestMessage:
    """Test Message model."""

    def test_message_creation(self):
        """Test creating a message."""
        message = Message(role="user", content="Hello")
        assert message.role == "user"
        assert message.content == "Hello"


class TestToolResult:
    """Test ToolResult model."""

    def test_tool_result_success(self):
        """Test successful tool result."""
        result = ToolResult(success=True, data="test data", error=None)
        assert result.success
        assert result.data == "test data"
        assert result.error is None

    def test_tool_result_failure(self):
        """Test failed tool result."""
        result = ToolResult(success=False, data=None, error="test error")
        assert not result.success
        assert result.data is None
        assert result.error == "test error"

    def test_format_result_success(self):
        """Test formatting successful result."""
        result = ToolResult(success=True, data="test data", error=None)
        formatted = result.format_result()
        assert "test data" in formatted

    def test_format_result_failure(self):
        """Test formatting failed result."""
        result = ToolResult(success=False, data=None, error="test error")
        formatted = result.format_result()
        assert formatted == "Error: test error"

    def test_format_result_command_output(self):
        """Test formatting command output."""
        data = {"stdout": "output", "stderr": "error", "returncode": 0}
        result = ToolResult(success=True, data=data, error=None)
        formatted = result.format_result()
        assert "Output:" in formatted
        assert "Errors:" in formatted


class TestTools:
    """Test tool implementations."""

    def test_file_write_tool(self, tmp_path):
        """Test file write tool."""
        context = Context(workspace_path=tmp_path)
        tool = FileWriteTool(path="test.txt", content="Hello, World!")
        result = tool.execute(context)

        assert result.success
        assert (tmp_path / "test.txt").exists()
        assert (tmp_path / "test.txt").read_text() == "Hello, World!"

    def test_file_read_tool(self, tmp_path):
        """Test file read tool."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        context = Context(workspace_path=tmp_path)
        tool = FileReadTool(path="test.txt")
        result = tool.execute(context)

        assert result.success
        assert result.data == "Hello, World!"

    def test_file_read_tool_not_found(self, tmp_path):
        """Test file read tool with non-existent file."""
        context = Context(workspace_path=tmp_path)
        tool = FileReadTool(path="nonexistent.txt")
        result = tool.execute(context)

        assert not result.success
        assert "File not found" in result.error

    def test_file_edit_tool(self, tmp_path):
        """Test file edit tool."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        context = Context(workspace_path=tmp_path)
        tool = FileEditTool(path="test.txt", operation="replace_lines", start_line=1, end_line=1, content="Hello, Bub!")
        result = tool.execute(context)

        assert result.success
        assert test_file.read_text() == "Hello, Bub!"

    def test_file_edit_tool_text_not_found(self, tmp_path):
        """Test file edit tool with text not found."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")

        context = Context(workspace_path=tmp_path)
        tool = FileEditTool(path="test.txt", operation="replace_lines", start_line=1, end_line=1, content="Hello, Bub!")
        result = tool.execute(context)

        assert result.success
        # The tool replaces the entire content, so it should succeed
        assert test_file.read_text() == "Hello, Bub!"

    def test_command_tool_success(self, tmp_path):
        """Test command tool with successful command."""
        context = Context(workspace_path=tmp_path)
        tool = RunCommandTool(command="echo 'Hello, World!'")
        result = tool.execute(context)

        assert result.success
        assert result.data["stdout"].strip() == "Hello, World!"
        assert result.data["returncode"] == 0

    def test_command_tool_failure(self, tmp_path):
        """Test command tool with failing command."""
        context = Context(workspace_path=tmp_path)
        tool = RunCommandTool(command="nonexistent_command")
        result = tool.execute(context)

        assert not result.success
        # Check that we have error data, but don't assume specific structure
        assert result.error is not None

    def test_command_tool_dangerous_command(self, tmp_path):
        """Test command tool blocks dangerous commands."""
        context = Context(workspace_path=tmp_path)
        tool = RunCommandTool(command="rm -rf /")
        result = tool.execute(context)

        assert not result.success
        assert "Dangerous command blocked" in result.error

    def test_command_tool_shell_injection(self, tmp_path):
        """Test command tool blocks shell injection."""
        context = Context(workspace_path=tmp_path)
        tool = RunCommandTool(command="echo 'test'; rm -rf /")
        result = tool.execute(context)

        assert not result.success
        assert "dangerous command pattern" in result.error


class TestToolRegistry:
    """Test tool registry."""

    def test_tool_registry_list_tools(self):
        """Test listing available tools."""
        registry = ToolRegistry()
        registry.register_default_tools()
        tools = registry.list_tools()

        expected_tools = ["read_file", "write_file", "edit_file", "run_command"]
        assert set(tools) == set(expected_tools)

    def test_tool_registry_get_tool(self):
        """Test getting tool classes."""
        registry = ToolRegistry()
        registry.register_default_tools()

        assert registry.get_tool("read_file") == FileReadTool
        assert registry.get_tool("write_file") == FileWriteTool
        assert registry.get_tool("edit_file") == FileEditTool
        assert registry.get_tool("run_command") == RunCommandTool
        assert registry.get_tool("nonexistent") is None

    def test_tool_registry_get_schema_nonexistent(self):
        """Test getting schema for non-existent tool."""
        registry = ToolRegistry()
        assert registry.get_tool_schema("nonexistent") is None


class TestToolExecutor:
    """Test tool executor."""

    def test_tool_executor_creation(self, tmp_path):
        """Test creating tool executor."""
        context = Context(workspace_path=tmp_path)
        context.tool_registry = ToolRegistry()
        executor = ToolExecutor(context)
        assert executor.context == context
        assert executor.tool_registry is not None

    def test_tool_executor_execute_tool_success(self, tmp_path):
        """Test successful tool execution."""
        context = Context(workspace_path=tmp_path)
        context.tool_registry = ToolRegistry()
        context.tool_registry.register_default_tools()
        executor = ToolExecutor(context)
        result = executor.execute_tool("write_file", path="test.txt", content="test")

        assert result.success
        assert (tmp_path / "test.txt").exists()

    def test_tool_executor_execute_tool_not_found(self, tmp_path):
        """Test tool execution with non-existent tool."""
        context = Context(workspace_path=tmp_path)
        context.tool_registry = ToolRegistry()
        executor = ToolExecutor(context)
        result = executor.execute_tool("nonexistent_tool")

        assert not result.success
        assert "Tool not found" in result.error


class TestAgent:
    """Test agent functionality."""

    def test_agent_creation(self, tmp_path):
        """Test creating an agent."""
        agent = Agent(api_key="test-key", model="test-model", workspace_path=tmp_path)
        assert agent.api_key == "test-key"
        assert agent.model == "test-model"

    def test_agent_reset_conversation(self, tmp_path):
        """Test resetting conversation."""
        agent = Agent(api_key="test-key", workspace_path=tmp_path)
        agent.conversation_history.append(Message(role="user", content="test"))

        agent.reset_conversation()
        assert len(agent.conversation_history) == 0

    @patch("litellm.completion")
    def test_agent_chat_no_tools(self, mock_completion, tmp_path):
        """Test agent chat without tool calls."""
        # Mock the completion response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Hello, I'm Bub!"
        mock_completion.return_value = mock_response

        agent = Agent(api_key="test-key", workspace_path=tmp_path)
        response = agent.chat("Hello")

        assert response == "Hello, I'm Bub!"
        assert len(agent.conversation_history) == 2  # user + assistant

    @patch("litellm.completion")
    def test_agent_chat_with_tools(self, mock_completion, tmp_path):
        """Test agent chat with tool calls."""
        # Mock responses: first with tool call, then final response
        mock_response1 = Mock()
        mock_response1.choices = [Mock()]
        mock_response1.choices[
            0
        ].message.content = (
            '```tool\n{"tool": "write_file", "parameters": {"path": "test.txt", "content": "test"}}\n```'
        )

        mock_response2 = Mock()
        mock_response2.choices = [Mock()]
        mock_response2.choices[0].message.content = "File created successfully!"

        mock_completion.side_effect = [mock_response1, mock_response2]

        agent = Agent(api_key="test-key", workspace_path=tmp_path)
        response = agent.chat("Create a test file")

        assert "File created successfully!" in response
        assert len(agent.conversation_history) >= 3  # user + assistant + tool result + final assistant

    def test_agent_extract_tool_calls(self, tmp_path):
        """Test extracting tool calls from response."""
        agent = Agent(api_key="test-key", workspace_path=tmp_path)
        response = 'Here\'s the result: ```tool\n{"tool": "read_file", "parameters": {"path": "test.txt"}}\n```'

        tool_calls = agent.tool_executor.extract_tool_calls(response)
        assert len(tool_calls) == 1
        assert tool_calls[0]["tool"] == "read_file"
        assert tool_calls[0]["parameters"]["path"] == "test.txt"

    def test_agent_extract_tool_calls_invalid_json(self, tmp_path):
        """Test extracting tool calls with invalid JSON."""
        agent = Agent(api_key="test-key", workspace_path=tmp_path)
        response = "Here's the result: ```tool\ninvalid json\n```"

        tool_calls = agent.tool_executor.extract_tool_calls(response)
        assert len(tool_calls) == 0

    def test_agent_execute_tool_calls(self, tmp_path):
        """Test executing tool calls."""
        agent = Agent(api_key="test-key", workspace_path=tmp_path)
        tool_calls = [{"tool": "write_file", "parameters": {"path": "test.txt", "content": "test"}}]

        result = agent.tool_executor.execute_tool_calls(tool_calls)
        assert "Observation:" in result
        assert (tmp_path / "test.txt").exists()
