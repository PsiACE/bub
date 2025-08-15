"""Core agent implementation for Bub.

Supports two execution modes:
- Legacy synchronous mode (default) executes tools inline.
- Evented mode (when provided an EventBus) publishes ReACT events and
  waits for observations, powered by Eventure + Huey runtime.
"""

import json
import re
import threading
from pathlib import Path
from typing import Callable, Optional

from any_llm import completion
from eventure import EventBus, EventLog
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from uuid_extension import uuid7

from .context import Context
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
        provider: str,
        model_name: str,
        api_key: str,
        api_base: Optional[str] = None,
        max_tokens: Optional[int] = None,
        workspace_path: Optional[Path] = None,
        system_prompt: Optional[str] = None,
        bus: Optional[EventBus] = None,
        event_log: Optional[EventLog] = None,
        context_window_tokens: int = 32000,
    ):
        self.provider = provider
        self.model_name = model_name
        self.api_key = api_key
        self.api_base = api_base
        self.max_tokens = max_tokens
        self.conversation_history: list[ChatCompletionMessageParam] = []
        self.context_window_tokens: int = context_window_tokens

        # Initialize context and tool registry
        self.context: Context = Context(workspace_path=workspace_path)
        self.tool_registry: ToolRegistry = ToolRegistry()
        self.tool_registry.register_default_tools()
        self.context.tool_registry = self.tool_registry  # type: ignore[assignment]

        self.tool_executor = ToolExecutor(self.context)

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

        # Evented runtime (required)
        self.bus: EventBus = bus or EventBus(EventLog())
        self.event_log: EventLog = event_log or self.bus.event_log
        self._evented: bool = True

    @property
    def model(self) -> str:
        """Get the full model string in provider/model format."""
        return f"{self.provider}/{self.model_name}"

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        self.conversation_history = []
        # Notify observers/renderer
        self._publish("agent.reset", {"reason": "user_requested"})

    def _publish(self, event_type: str, data: dict) -> None:
        self.bus.publish(event_type, data)

    def _wait_for_observation(self, action_id: str, timeout_seconds: float = 30.0) -> dict:
        done = threading.Event()
        payload: dict = {}

        def on_observation(event, _aid=action_id, _payload=payload, _done=done) -> None:
            data = event.data
            if data.get("id") == _aid:
                _payload.update(data)
                _done.set()

        unsubscribe = self.bus.subscribe("agent.observation", on_observation)
        try:
            done.wait(timeout=timeout_seconds)
        finally:
            unsubscribe()
        return payload

    def _process_tool_calls(self, tool_calls: list[dict], on_step: Optional[Callable[[str, str], None]]) -> None:
        for tool_call in tool_calls:
            tool_name = tool_call.get("tool")
            parameters = tool_call.get("parameters", {})
            if not tool_name:
                continue
            action_id = str(uuid7())
            # Subscribe BEFORE publishing action to avoid race (immediate execution)
            done = threading.Event()
            payload: dict = {}

            def on_observation(event, _aid=action_id, _payload=payload, _done=done) -> None:
                data = event.data
                if data.get("id") == _aid:
                    _payload.update(data)
                    _done.set()

            unsubscribe = self.bus.subscribe("agent.observation", on_observation)
            try:
                self._publish("agent.action", {"id": action_id, "tool": tool_name, "input": parameters})
                # Extend wait based on tool-specific timeout if provided
                wait_seconds = float(parameters.get("timeout", 30)) + 5.0
                done.wait(timeout=wait_seconds)
            finally:
                unsubscribe()
            obs_payload = payload
            if not obs_payload:
                obs_text = f'Observation: {{"ok": false, "error": "Tool {tool_name} timed out"}}'
                self.conversation_history.append({"role": "user", "content": obs_text})
                if on_step:
                    on_step("observation", obs_text)
                continue
            observation = json.dumps(obs_payload.get("result", {}), ensure_ascii=False)
            obs_text = f"Observation: {observation}"
            self.conversation_history.append({"role": "user", "content": obs_text})
            if on_step:
                on_step("observation", obs_text)
        # Advance tick after processing observations
        self.event_log.advance_tick()

    def _strip_final_answer(self, text: str) -> str:
        """Remove any 'Final Answer:' section from a ReACT message (used when tools will run)."""
        idx = text.find("Final Answer:")
        return text if idx == -1 else text[:idx].rstrip()

    def _extract_final_answer(self, text: str) -> Optional[str]:
        m = re.search(r"Final Answer:\s*(.+)\s*$", text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else None

    def _estimate_tokens_for_text(self, text: str) -> int:
        # Approximate: ~4 chars per token
        return max(1, len(text) // 4)

    def _estimate_tokens_for_messages(self, messages: list[ChatCompletionMessageParam]) -> int:
        total = 0
        for m in messages:
            content = str(m.get("content", ""))
            total += self._estimate_tokens_for_text(content) + 4  # small overhead per message
        return total

    def _build_messages(self) -> list[ChatCompletionMessageParam]:
        system_msgs: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "system", "content": self.context.build_context_message()},
        ]
        history = list(self.conversation_history)
        # Reserve room for model output; default to 1000 if unspecified
        output_budget = self.max_tokens or 1000
        # Keep a safety margin for tool/use overhead
        budget = max(1000, self.context_window_tokens - output_budget - 500)
        while True:
            msgs = system_msgs + history
            if self._estimate_tokens_for_messages(msgs) <= budget:
                return msgs
            if not history:
                return msgs
            # Trim from the oldest entries (drop oldest user+assistant pair when possible)
            history = history[2:] if len(history) >= 2 else history[1:]

    def chat(self, message: str, on_step: Optional[Callable[[str, str], None]] = None) -> str:
        """Chat with the agent. If on_step is provided, call it with each intermediate message/observation."""
        self.conversation_history.append({"role": "user", "content": message})

        # Evented: advance tick and publish user input
        self.event_log.advance_tick()
        self._publish("user.input", {"message": message})

        while True:
            messages: list[ChatCompletionMessageParam] = self._build_messages()

            try:
                response: ChatCompletion = completion(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    api_key=self.api_key,
                    api_base=self.api_base,
                )
                assistant_message = str(response.choices[0].message.content)

                tool_calls = self.tool_executor.extract_tool_calls(assistant_message)
                if not tool_calls:
                    # Publish explicit final event for renderer clarity
                    final = self._extract_final_answer(assistant_message) or assistant_message
                    self.conversation_history.append({"role": "assistant", "content": assistant_message})
                    self._publish("agent.final", {"content": final})
                    if on_step:
                        on_step("assistant", final)
                    return final

                # Evented tool execution
                # Do not surface premature Final Answer lines prior to tool execution
                cleaned = self._strip_final_answer(assistant_message)
                self.conversation_history.append({"role": "assistant", "content": cleaned})
                self._publish("agent.thought", {"content": cleaned})
                if on_step:
                    on_step("assistant", cleaned)
                self._process_tool_calls(tool_calls, on_step)
                # Immediately get the final answer after tools complete
                messages = self._build_messages()
                response2: ChatCompletion = completion(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    api_key=self.api_key,
                    api_base=self.api_base,
                )
                final_message = str(response2.choices[0].message.content)
                self.conversation_history.append({"role": "assistant", "content": final_message})
                final = self._extract_final_answer(final_message) or final_message
                self._publish("agent.final", {"content": final})
                if on_step:
                    on_step("assistant", final)
            except Exception as e:
                error_message = f"Error communicating with AI: {e!s}"
                self.conversation_history.append({"role": "assistant", "content": error_message})
                if on_step:
                    on_step("error", error_message)
                return error_message
            else:
                return final
