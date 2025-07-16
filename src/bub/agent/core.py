"""Core agent implementation for Bub."""

from pathlib import Path
from typing import Callable, Optional

import litellm

from .context import Context, Message
from .tools import ToolExecutor, ToolRegistry


class ReActPromptFormatter:
    """Formats ReAct prompts by combining principles, system prompt, and examples."""

    REACT_PRINCIPLES = """You are an AI assistant with access to tools. When you need to use a tool, follow this format:

Thought: Do I need to use a tool? Yes/No. If yes, which one and with what input?
Action: <tool_name>
Action Input: <JSON parameters for the tool>

After the tool is executed, you will see:
Observation: <tool output>

You can use multiple Thought/Action/Action Input/Observation steps as needed (ReAct pattern). When you have a final answer, reply with:

Final Answer: <your answer to the user>

If you do not need a tool, just reply with Final Answer."""

    REACT_EXAMPLE = """Example:
Thought: I need to list files in the workspace.
Action: run_command
Action Input: {"command": "ls"}
Observation: <output of ls>
Thought: Now I can answer the user.
Final Answer: The files in your workspace are ...

Available tools and their parameters will be provided in the context.

Always be helpful, accurate, and follow best practices."""

    def format_prompt(self, system_prompt: str) -> str:
        """Format a complete ReAct prompt with principles, system prompt, and examples."""
        return f"{self.REACT_PRINCIPLES}\n\n{system_prompt}\n\n{self.REACT_EXAMPLE}"


class Agent:
    """Main AI agent for Bub."""

    def __init__(
        self,
        api_key: str,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        workspace_path: Optional[Path] = None,
        system_prompt: Optional[str] = None,
    ):
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.max_tokens = max_tokens
        self.conversation_history: list[Message] = []

        # Initialize context and tool registry
        self.context: Context = Context(workspace_path=workspace_path)
        self.tool_registry: ToolRegistry = ToolRegistry()
        self.tool_registry.register_default_tools()
        self.context.tool_registry = self.tool_registry  # type: ignore[assignment]

        self.tool_executor = ToolExecutor(self.context)

        # Store custom system prompt if provided
        self.custom_system_prompt = system_prompt

        # Use ReAct principles as the main system prompt
        self.prompt_formatter = ReActPromptFormatter()
        self.system_prompt = self.prompt_formatter.REACT_PRINCIPLES

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        self.conversation_history = []

    def chat(self, message: str, on_step: Optional[Callable[[str, str], None]] = None) -> str:
        """Chat with the agent. If on_step is provided, call it with each intermediate message/observation."""
        self.conversation_history.append(Message(role="user", content=message))

        while True:
            context_msg = self.context.build_context_message()

            # Add system prompt to context if available
            system_prompt = self.custom_system_prompt or self.context.get_system_prompt()
            if system_prompt:
                context_msg += f"\n\n[System Instructions]\n{system_prompt}"

            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "system", "content": context_msg},
            ]
            messages.extend([{"role": msg.role, "content": msg.content} for msg in self.conversation_history])

            try:
                response = litellm.completion(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    api_key=self.api_key,
                    base_url=self.api_base,
                )
                assistant_message = str(response.choices[0].message.content)
                self.conversation_history.append(Message(role="assistant", content=assistant_message))
                if on_step:
                    on_step("assistant", assistant_message)

                tool_calls = self.tool_executor.extract_tool_calls(assistant_message)

                if tool_calls:
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("tool")
                        parameters = tool_call.get("parameters", {})
                        if not tool_name:
                            continue
                        result = self.tool_executor.execute_tool(tool_name, **parameters)
                        observation = f"Observation: {result.format_result()}"
                        self.conversation_history.append(Message(role="user", content=observation))
                        if on_step:
                            on_step("observation", observation)
                    continue
                else:
                    return assistant_message

            except Exception as e:
                error_message = f"Error communicating with AI: {e!s}"
                self.conversation_history.append(Message(role="assistant", content=error_message))
                if on_step:
                    on_step("error", error_message)
                return error_message
