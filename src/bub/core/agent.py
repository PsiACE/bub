"""Core agent implementation for Bub."""

import contextlib
import re
from pathlib import Path
from typing import Any, Callable, Optional

from any_llm import completion  # type: ignore[import-untyped]
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam

from .context import AgentContext
from .tools import ToolRegistry


class ReActPromptFormatter:
    """Formats ReAct prompts by combining principles, system prompt, and examples."""

    REACT_PRINCIPLES = """You are an AI assistant with access to tools. When you need to use a tool, follow this format:

Thought: Do I need to use a tool? Yes/No. If yes, which one and with what input?
Action: <tool_name>
Action Input: <JSON parameters for the tool>

After the tool is executed, you will see:
Observation: <tool output>

You can use multiple Thought/Action/Action Input/Observation steps as needed for complex reasoning. When you have a final answer, reply with:

Final Answer: <your answer to the user>

CRITICAL RULES:
1. If you need a tool, provide ONLY the Thought/Action/Action Input in your response
2. After seeing the Observation, provide your Final Answer
3. Do NOT include Final Answer in the same response as Action/Action Input
4. Only continue with more Thought/Action steps if you need additional tools or information
5. When the user asks for specific information (files, command output, etc.), your Final Answer MUST include the actual data
6. NEVER give generic responses like "Here's the file listing:" - ALWAYS include the actual content
7. If the user asks for file listings, show the actual files. If they ask for command output, show the actual output.
8. ALWAYS end your response with "Final Answer:" when providing the final response to the user
9. If you see tool output in the Observation, include that output in your Final Answer

If you do not need a tool, just reply with Final Answer."""

    REACT_EXAMPLE = """Example:

Step 1 - Tool Usage:
Thought: I need to list files in the workspace.
Action: run_command
Action Input: {"command": "ls"}

Step 2 - After Observation:
Observation: STDOUT:
file1.txt
file2.py
README.md

Return code: 0
Thought: The user asked for a file listing, so I must provide the actual files in my final answer.
Final Answer: Here are the files in your workspace:

file1.txt
file2.py
README.md

Available tools and their parameters will be provided in the context.

Always be helpful, accurate, and follow best practices."""

    def format_prompt(self, system_prompt: str) -> str:
        """Format a complete ReAct prompt with principles, system prompt, and examples."""
        return f"{self.REACT_PRINCIPLES}\n\n{system_prompt}\n\n{self.REACT_EXAMPLE}"


class Agent:
    """Main AI agent for Bub with ReAct pattern support."""

    def __init__(
        self,
        provider: str,
        model_name: str,
        api_key: str,
        api_base: Optional[str] = None,
        max_tokens: Optional[int] = None,
        workspace_path: Optional[Path] = None,
        system_prompt: Optional[str] = None,
        config: Optional[Any] = None,
        timeout_seconds: int = 30,
        max_iterations: int = 10,
    ) -> None:
        """Initialize the agent.

        Args:
            provider: LLM provider (e.g., 'openai', 'anthropic')
            model_name: Model name (e.g., 'gpt-4', 'claude-3')
            api_key: API key for the provider
            api_base: Optional API base URL
            max_tokens: Maximum tokens for responses
            workspace_path: Path to workspace
            system_prompt: System prompt for the agent
            config: Configuration object
            timeout_seconds: Timeout for AI responses in seconds
            max_iterations: Maximum number of tool execution cycles
        """
        self.provider = provider
        self.model = model_name
        self.api_key = api_key
        self.api_base = api_base
        self.max_tokens = max_tokens
        self.workspace_path = workspace_path or Path.cwd()
        self.conversation_history: list[ChatCompletionMessageParam] = []
        self.timeout_seconds = timeout_seconds
        self.max_iterations = max_iterations

        # Initialize components
        self.context = AgentContext(
            provider=provider,
            model_name=model_name,
            api_key=api_key,
            api_base=api_base,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            workspace_path=self.workspace_path,
        )
        self.tool_registry = ToolRegistry(workspace_path=self.workspace_path)

        # Set the tool registry in the context so it's available for context building
        self.context.tool_registry = self.tool_registry

        # Store custom system prompt if provided
        self.custom_system_prompt = system_prompt

        self.prompt_formatter = ReActPromptFormatter()
        # Use format_prompt to generate the full system prompt
        if self.custom_system_prompt:
            self.system_prompt = self.prompt_formatter.format_prompt(self.custom_system_prompt)
        else:
            # Use config default if not provided
            config_prompt = self.context.get_system_prompt()
            self.system_prompt = self.prompt_formatter.format_prompt(config_prompt)

    def chat(self, message: str, on_step: Optional[Callable[[str, str], None]] = None, debug_mode: bool = False) -> str:
        """Chat with the agent using ReAct pattern.

        Args:
            message: User message
            on_step: Optional callback for each step
            debug_mode: Whether to show ReAct process details

        Returns:
            Agent response
        """
        self.conversation_history.append({"role": "user", "content": message})

        if on_step:
            on_step("assistant", "Processing your request...")

        # Add loop control to prevent infinite loops
        iteration_count = 0

        while iteration_count < self.max_iterations:
            try:
                iteration_count += 1

                if on_step and iteration_count > 1:
                    on_step("observation", f"Processing step {iteration_count}...")

                assistant_message = self._get_ai_response(on_step, debug_mode)

                # Extract and execute tool calls
                tool_calls = self._extract_tool_calls(assistant_message)
                has_final_answer = "Final Answer:" in assistant_message

                if tool_calls:
                    # Execute tools first
                    self._execute_tool_calls(tool_calls, on_step)

                    # If there's also a Final Answer in this response, extract and return it
                    if has_final_answer:
                        final_answer = self._extract_final_answer(assistant_message)
                        return final_answer

                    # Continue loop for next AI response after tool execution
                    continue
                else:
                    # No tools, just return the response (with or without Final Answer)
                    if debug_mode:
                        # In debug mode, we already emitted the steps, so return the extracted final answer
                        final_answer = self._extract_final_answer(assistant_message)
                        return final_answer
                    else:
                        # In non-debug mode, return the already extracted final answer
                        return assistant_message

            except Exception as e:
                error_message = f"Error communicating with AI (iteration {iteration_count}): {e!s}"
                self.conversation_history.append({"role": "assistant", "content": error_message})
                if on_step:
                    on_step("error", error_message)
                return error_message

        # If we reach here, we've exceeded max iterations
        error_message = f"The AI has reached the maximum number of steps ({self.max_iterations}) while processing your request. This might indicate a complex task that requires more steps, or the AI might be stuck in a loop. You can try:\n\n1. Breaking down your request into smaller parts\n2. Being more specific about what you need\n3. Checking if your request is clear and achievable"
        self.conversation_history.append({"role": "assistant", "content": error_message})
        if on_step:
            on_step("error", error_message)
        return error_message

    def _get_ai_response(self, on_step: Optional[Callable[[str, str], None]], debug_mode: bool) -> str:
        """Get AI response and handle debug mode."""
        import signal

        context_message = self.context.build_context_message()
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": context_message},
        ]
        messages.extend(self.conversation_history)

        if on_step:
            on_step("observation", f"Using {self.model}...")

        # Add timeout protection with graceful handling
        timeout_occurred = False

        def timeout_handler(signum: int, frame: Any) -> None:
            nonlocal timeout_occurred
            timeout_occurred = True

        # Set up timeout (only on Unix-like systems)
        try:
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.timeout_seconds)
        except (AttributeError, OSError):
            # Windows doesn't support SIGALRM, skip timeout
            pass

        try:
            response: ChatCompletion = completion(
                model=f"{self.provider}/{self.model}",
                messages=messages,
                max_tokens=self.max_tokens,
                api_key=self.api_key,
                api_base=self.api_base,
            )
        except Exception:
            # Clear the alarm first
            with contextlib.suppress(AttributeError, OSError):
                signal.alarm(0)

            # Check if it was a timeout
            if timeout_occurred:
                timeout_message = f"The AI is taking longer than {self.timeout_seconds} seconds to respond. This might be due to a complex request or network issues. Please try again with a simpler request or check your connection."
                self.conversation_history.append({"role": "assistant", "content": timeout_message})
                if on_step:
                    on_step("error", timeout_message)
                return timeout_message
            else:
                # Re-raise other exceptions
                raise
        finally:
            # Clear the alarm
            with contextlib.suppress(AttributeError, OSError):
                signal.alarm(0)

        assistant_message = str(response.choices[0].message.content)
        self.conversation_history.append({"role": "assistant", "content": assistant_message})

        # Check if this response contains tool calls
        tool_calls = self._extract_tool_calls(assistant_message)

        if debug_mode:
            self._emit_react_steps(assistant_message, on_step)
        elif not tool_calls:
            # In non-debug mode, only emit assistant message if no tools are being used
            final_answer = self._extract_final_answer(assistant_message)
            if on_step:
                on_step("assistant", final_answer)

        return assistant_message

    def _execute_tool_calls(
        self, tool_calls: list[dict[str, Any]], on_step: Optional[Callable[[str, str], None]]
    ) -> None:
        """Execute tool calls and add observations to conversation."""
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool")
            parameters = tool_call.get("parameters", {})

            if not tool_name:
                continue

            result = self._execute_tool(tool_name, **parameters)
            observation = f"Observation: {result}"

            self.conversation_history.append({"role": "user", "content": observation})
            if on_step:
                on_step("observation", observation)

    def _extract_tool_calls(self, message: str) -> list[dict[str, Any]]:
        """Extract tool calls from ReAct format message."""
        tool_calls = []

        # Look for Action: and Action Input: patterns
        action_match = re.search(r"Action:\s*(\w+)", message, re.IGNORECASE)
        action_input_match = re.search(r"Action Input:\s*(.+)", message, re.IGNORECASE | re.DOTALL)

        if action_match and action_input_match:
            tool_name = action_match.group(1).strip()
            action_input = action_input_match.group(1).strip()

            # Clean up the action input - remove any trailing content
            if "\n" in action_input:
                action_input = action_input.split("\n")[0].strip()

            # Remove quotes if present
            action_input = action_input.strip("\"'")

            # Try to parse JSON parameters
            try:
                import json

                parameters = json.loads(action_input)
            except (json.JSONDecodeError, ValueError):
                # If not valid JSON, treat as simple string parameter
                parameters = {"command": action_input}

            tool_calls.append({"tool": tool_name, "parameters": parameters})

        return tool_calls

    def _execute_tool(self, tool_name: str, **parameters: Any) -> str:
        """Execute a tool and return the result."""
        try:
            # Get tool class from registry
            tool_class = self.tool_registry._tools.get(tool_name)
            if not tool_class:
                return f"Tool '{tool_name}' not found"

            # Create tool instance with parameters
            tool_instance = tool_class(**parameters)

            # Execute the tool with context
            result = tool_instance.execute(self.context)

            if result.data and "stdout" in result.data:
                # Format output to show all information regardless of success/failure
                output_parts = []

                # Add stdout if present
                if result.data["stdout"]:
                    output_parts.append(f"STDOUT:\n{result.data['stdout']}")

                # Add stderr if present
                if result.data.get("stderr"):
                    output_parts.append(f"STDERR:\n{result.data['stderr']}")

                # Add return code
                returncode = result.data.get("returncode", 0)
                output_parts.append(f"Return code: {returncode}")

                # Add error message if command failed
                if not result.success and result.error:
                    output_parts.append(f"Error: {result.error}")

                return "\n\n".join(output_parts) if output_parts else "Command executed successfully"

            # Handle other tool types
            if result.success:
                return str(result.data) if result.data else "Command executed successfully"
            else:
                return f"Tool execution failed: {result.error}"
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e!s}"

    def _emit_react_steps(self, message: str, on_step: Optional[Callable[[str, str], None]]) -> None:
        """Emit ReAct steps for debug mode."""
        if not on_step:
            return

        # Parse ReAct components with simpler, more reliable regex patterns
        thought_pattern = r"Thought:\s*(.*?)(?=\n(?:Action:|Final Answer:)|$)"
        action_pattern = r"Action:\s*(.*?)(?=\n(?:Action Input:|Final Answer:)|$)"
        action_input_pattern = r"Action Input:\s*(.*?)(?=\n(?:Observation:|Final Answer:)|$)"
        final_answer_pattern = r"Final Answer:\s*(.*?)(?=\n|$)"

        thought_match = re.search(thought_pattern, message, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        action_match = re.search(action_pattern, message, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        action_input_match = re.search(action_input_pattern, message, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        final_answer_match = re.search(final_answer_pattern, message, re.IGNORECASE | re.MULTILINE | re.DOTALL)

        if thought_match:
            thought_content = thought_match.group(1).strip()
            # Clean up thought content - remove any trailing action/input
            if "Action:" in thought_content:
                thought_content = thought_content.split("Action:")[0].strip()
            on_step("taao_thought", thought_content)

        if action_match:
            action_content = action_match.group(1).strip()
            # Clean up action content - remove any trailing input
            if "Action Input:" in action_content:
                action_content = action_content.split("Action Input:")[0].strip()
            on_step("taao_action", action_content)

        if action_input_match:
            action_input_content = action_input_match.group(1).strip()
            # Clean up action input content - remove any trailing observation
            if "Observation:" in action_input_content:
                action_input_content = action_input_content.split("Observation:")[0].strip()
            on_step("taao_action_input", action_input_content)

        if final_answer_match:
            final_answer_content = final_answer_match.group(1).strip()
            on_step("assistant", final_answer_content)
        else:
            # If no final answer but there's a thought, use the thought as the final answer
            # This handles cases where the AI thinks about the result but doesn't provide explicit Final Answer
            if thought_match and not action_match:
                thought_content = thought_match.group(1).strip()
                # Extract the actual tool output from the conversation history if available
                # For now, just use the thought content as the final answer
                on_step("assistant", thought_content)
            else:
                # If no final answer and no relevant thought, use the whole response
                on_step("assistant", message)

    def _extract_final_answer(self, message: str) -> str:
        """Extract the Final Answer from a ReAct message."""
        final_answer_match = re.search(r"Final Answer:\s*(.*)", message, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        if final_answer_match:
            return final_answer_match.group(1).strip()
        return message.strip()

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        self.conversation_history = []

    def add_tool(self, tool: Any) -> None:
        """Add a tool to the registry.

        Args:
            tool: Tool to add
        """
        self.tool_registry.register_tool(tool)
