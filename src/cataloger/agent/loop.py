"""Core agent loop implementation."""

import json
from typing import Any

import anthropic
import structlog

from ..container.runtime import ContainerRuntime, ExecutionError
from .tools import get_tool_schemas

log = structlog.get_logger()


class AgentTerminated(Exception):
    """Raised when the agent calls submit_html."""

    def __init__(self, html_content: str):
        self.html_content = html_content
        super().__init__("Agent submitted HTML")


class AgentLoop:
    """Manages the agent execution loop with tool calling.

    The agent receives a prompt, makes tool calls (execute_python or submit_html),
    receives results, and continues until it calls submit_html.
    """

    def __init__(
        self,
        client: anthropic.Anthropic,
        runtime: ContainerRuntime,
        model: str = "claude-sonnet-4-0",
        max_tokens: int = 100_000,
        temperature: float = 0.0,
    ):
        self.client = client
        self.runtime = runtime
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.tools = get_tool_schemas()
        self._token_usage = {"input": 0, "output": 0}

    def run(self, system_prompt: str, context: dict[str, Any]) -> str:
        """Run the agent loop until it submits HTML.

        Args:
            system_prompt: The agent's instructions
            context: Context to inject (e.g., {"tables": [...]} for cataloging agent)

        Returns:
            The submitted HTML content

        Raises:
            RuntimeError: If agent exceeds token budget or max iterations
        """
        # Initialize conversation with context
        messages = [
            {
                "role": "user",
                "content": f"Context:\n```json\n{json.dumps(context, indent=2)}\n```\n\nBegin your analysis.",
            }
        ]

        iteration = 0
        max_iterations = 50  # Safety limit

        log.info(
            "agent.loop.start",
            model=self.model,
            context_keys=list(context.keys()),
        )

        try:
            while iteration < max_iterations:
                iteration += 1

                # Call Claude API
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=8192,  # Per-request limit (increased for HTML generation)
                    temperature=self.temperature,
                    system=system_prompt,
                    messages=messages,
                    tools=self.tools,
                )

                # Track token usage
                self._token_usage["input"] += response.usage.input_tokens
                self._token_usage["output"] += response.usage.output_tokens

                log.info(
                    "agent.loop.iteration",
                    iteration=iteration,
                    stop_reason=response.stop_reason,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    total_input=self._token_usage["input"],
                    total_output=self._token_usage["output"],
                )

                # Check token budget
                if self._token_usage["output"] > self.max_tokens:
                    raise RuntimeError(
                        f"Agent exceeded token budget: {self._token_usage['output']} > {self.max_tokens}"
                    )

                # Add assistant message
                messages.append({"role": "assistant", "content": response.content})

                # Handle stop reason
                if response.stop_reason == "end_turn":
                    # Agent finished without tool use (shouldn't happen)
                    raise RuntimeError("Agent ended conversation without submitting HTML")

                if response.stop_reason == "tool_use":
                    # Process tool calls
                    tool_results = []

                    for block in response.content:
                        if block.type == "tool_use":
                            try:
                                result = self._handle_tool_call(block)
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": result,
                                    }
                                )
                            except AgentTerminated as e:
                                # Agent submitted HTML - return it
                                log.info(
                                    "agent.loop.complete",
                                    iterations=iteration,
                                    tokens=self._token_usage,
                                )
                                return e.html_content

                    # Add tool results to conversation
                    messages.append({"role": "user", "content": tool_results})

                elif response.stop_reason == "max_tokens":
                    # Hit per-request token limit
                    log.warning("agent.loop.max_tokens_per_request", iteration=iteration)

                    # Check if there are any tool calls in the truncated response
                    # (tool calls can be complete even if text content was cut off)
                    tool_results = []
                    has_tool_calls = False

                    for block in response.content:
                        if block.type == "tool_use":
                            has_tool_calls = True
                            try:
                                result = self._handle_tool_call(block)
                                tool_results.append(
                                    {
                                        "type": "tool_result",
                                        "tool_use_id": block.id,
                                        "content": result,
                                    }
                                )
                            except AgentTerminated as e:
                                # Agent submitted HTML - return it
                                log.info(
                                    "agent.loop.complete",
                                    iterations=iteration,
                                    tokens=self._token_usage,
                                )
                                return e.html_content

                    # If there were tool calls, add results to conversation
                    if has_tool_calls:
                        messages.append({"role": "user", "content": tool_results})
                    # Otherwise just continue (pure text was truncated)

                else:
                    raise RuntimeError(f"Unexpected stop reason: {response.stop_reason}")

            raise RuntimeError(f"Agent exceeded max iterations: {max_iterations}")

        except Exception as e:
            log.error(
                "agent.loop.error",
                error=str(e),
                iteration=iteration,
                tokens=self._token_usage,
            )
            raise

    def _handle_tool_call(self, tool_use: Any) -> str:
        """Handle a single tool call.

        Args:
            tool_use: The tool_use block from Claude's response

        Returns:
            String result to return to the agent

        Raises:
            AgentTerminated: If the agent calls submit_html
        """
        tool_name = tool_use.name
        tool_input = tool_use.input

        log.info("agent.tool_call", tool=tool_name, input_len=len(str(tool_input)))

        if tool_name == "execute_python":
            # Check if code field exists (might be truncated if max_tokens hit)
            if "code" not in tool_input:
                return "Error: execute_python call was truncated. Please retry with complete code."
            code = tool_input["code"]
            try:
                output = self.runtime.execute(code)
                log.info("agent.tool_result", tool="execute_python", output_len=len(output))
                return output
            except ExecutionError as e:
                error_msg = str(e)
                log.warning("agent.execution_error", error=error_msg)
                return f"Execution error:\n{error_msg}"

        elif tool_name == "submit_html":
            # Check if content field exists (might be truncated if max_tokens hit)
            if "content" not in tool_input:
                return "Error: submit_html call was truncated. Please try again with complete HTML content."
            content = tool_input["content"]
            log.info("agent.submit_html", content_len=len(content))
            raise AgentTerminated(content)

        else:
            return f"Unknown tool: {tool_name}"

    def get_token_usage(self) -> dict[str, int]:
        """Return the total token usage for this agent run."""
        return self._token_usage.copy()
