"""
Agent Loop Engine
-----------------
Implements the while(tool_use) pattern from Claude Code.
Each agent is a single loop: send message → if tool_use, execute tools → feed results back → repeat.
The loop IS the agent. No critics, no role-switching, no orchestration.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field

import anthropic

from tools import TOOL_EXECUTORS

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result of an agent run."""
    final_text: str = ""
    tool_calls: int = 0
    iterations: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0
    stopped_reason: str = ""


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    system_prompt: str
    tools: list[dict]
    model: str = "claude-opus-4-20250514"
    max_tokens: int = 16384
    max_iterations: int = 50  # safety valve — most agents should stop themselves
    temperature: float = 0.0  # deterministic for financial work


def run_agent(
    config: AgentConfig,
    user_message: str,
    on_tool_call: callable | None = None,
    on_text: callable | None = None,
) -> AgentResult:
    """
    Run an agent in a while(tool_use) loop.

    The agent receives the system prompt and user message, then loops:
    1. Send messages to Claude
    2. If response contains tool_use blocks, execute them
    3. Feed tool results back as the next message
    4. Repeat until Claude responds with end_turn (no tool use)

    Args:
        config: Agent configuration (name, system prompt, tools, model, etc.)
        user_message: The initial user message to start the agent
        on_tool_call: Optional callback(tool_name, tool_input) for logging
        on_text: Optional callback(text) for streaming text output
    """
    client = anthropic.Anthropic()
    result = AgentResult()
    start_time = time.time()

    messages = [{"role": "user", "content": user_message}]

    for iteration in range(config.max_iterations):
        result.iterations = iteration + 1

        logger.info(
            "[%s] Iteration %d — sending %d messages",
            config.name, iteration + 1, len(messages),
        )

        try:
            response = client.messages.create(
                model=config.model,
                max_tokens=config.max_tokens,
                system=config.system_prompt,
                tools=config.tools,
                messages=messages,
                temperature=config.temperature,
            )
        except anthropic.APIError as e:
            logger.error("[%s] API error: %s", config.name, e)
            result.stopped_reason = f"api_error: {e}"
            break

        # Track token usage
        if response.usage:
            result.input_tokens += response.usage.input_tokens
            result.output_tokens += response.usage.output_tokens

        # Process response content blocks
        tool_uses = []
        text_parts = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
                if on_text:
                    on_text(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)
                result.tool_calls += 1
                if on_tool_call:
                    on_tool_call(block.name, block.input)

        # Save the last text output
        if text_parts:
            result.final_text = "\n".join(text_parts)

        # If no tool use, the agent is done
        if response.stop_reason == "end_turn" and not tool_uses:
            result.stopped_reason = "end_turn"
            logger.info(
                "[%s] Completed after %d iterations, %d tool calls",
                config.name, result.iterations, result.tool_calls,
            )
            break

        if not tool_uses:
            result.stopped_reason = f"no_tool_use (stop_reason={response.stop_reason})"
            break

        # Execute tools and collect results
        assistant_message = {"role": "assistant", "content": response.content}
        messages.append(assistant_message)

        tool_results = []
        for tool_use in tool_uses:
            tool_result = _execute_tool(tool_use.name, tool_use.input)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": tool_result,
            })

            logger.info(
                "[%s] Tool: %s → %d chars",
                config.name, tool_use.name, len(tool_result),
            )

        messages.append({"role": "user", "content": tool_results})

    else:
        result.stopped_reason = "max_iterations"
        logger.warning(
            "[%s] Hit max iterations (%d)", config.name, config.max_iterations,
        )

    result.duration_seconds = time.time() - start_time
    return result


def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool by name with the given input."""
    executor = TOOL_EXECUTORS.get(tool_name)
    if executor is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        return executor(**tool_input)
    except TypeError as e:
        # Wrong arguments — return error so agent can self-correct
        return json.dumps({"error": f"Invalid arguments for {tool_name}: {str(e)}"})
    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_name)
        return json.dumps({"error": f"Tool {tool_name} failed: {str(e)}"})
