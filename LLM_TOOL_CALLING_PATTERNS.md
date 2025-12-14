# LLM Tool Calling Implementation Patterns

This document describes the tool calling patterns used in the `cataloger` project. Use this as a reference when implementing similar LLM-powered agentic systems in other projects.

## Overview

The cataloger project implements a clean, production-ready LLM tool calling architecture using:
- **LLM Provider**: Anthropic Claude API (native tool support)
- **Tool Philosophy**: Minimalist "Armin Ronacher Tools" pattern - just 2 tools
- **Execution Model**: Stateful, persistent Python environment in Docker containers
- **Control Flow**: Agentic loop with token/iteration safety limits

## Architecture Components

### 1. Tool Schema Definition (`src/cataloger/agent/tools.py`)

Tools are defined using JSON Schema format compatible with Anthropic's Claude API:

```python
"""Tool schemas for agent execution.

Following Armin Ronacher's "Tools" pattern, we provide just two tools:
- execute_python(code): Run Python code in the container
- submit_html(content): Submit the final HTML report
"""

TOOL_SCHEMAS = [
    {
        "name": "execute_python",
        "description": (
            "Execute Python code in a persistent session. "
            "State persists across calls, like IPython. "
            "Returns a single output stream with expression results, print statements, and errors. "
            "Available libraries: ibis, boto3, polars, pandas. "
            "Environment variables: DB_CONNECTION_STRING, AWS_* for S3 access, S3_BUCKET."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
                }
            },
            "required": ["code"],
        },
    },
    {
        "name": "submit_html",
        "description": (
            "Submit the final HTML report. This terminates the agent loop. "
            "The HTML should be a complete, self-contained document with inline CSS. "
            "Keep tables to ~20 rows for readability."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Complete HTML document",
                }
            },
            "required": ["content"],
        },
    },
]

def get_tool_schemas() -> list[dict[str, Any]]:
    """Return the tool schemas for the agent."""
    return TOOL_SCHEMAS
```

**Key Principles:**
- Use descriptive `description` fields that explain tool behavior to the LLM
- Include usage hints (available libraries, environment variables, output format)
- Follow JSON Schema spec for `input_schema`
- Keep tool set minimal - only what's strictly necessary

### 2. Agent Loop (`src/cataloger/agent/loop.py`)

The `AgentLoop` class orchestrates the complete tool calling workflow:

#### Initialization

```python
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
        self.max_tokens = max_tokens  # Total output budget
        self.temperature = temperature
        self.tools = get_tool_schemas()  # Load tool schemas
        self._token_usage = {"input": 0, "output": 0}
```

**Configuration:**
- Accept LLM client (Anthropic) as dependency
- Accept runtime (tool executor) as dependency
- Track cumulative token usage across all iterations
- Set safety limits (max_tokens budget, temperature)

#### Main Loop

```python
def run(self, system_prompt: str, context: dict[str, Any]) -> str:
    """Run the agent loop until it submits HTML."""

    # 1. Initialize conversation with context
    messages = [
        {
            "role": "user",
            "content": f"Context:\n```json\n{json.dumps(context, indent=2)}\n```\n\nBegin your analysis.",
        }
    ]

    iteration = 0
    max_iterations = 50  # Safety limit

    try:
        while iteration < max_iterations:
            iteration += 1

            # 2. Call Claude API with tools
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,  # Per-request limit
                temperature=self.temperature,
                system=system_prompt,
                messages=messages,
                tools=self.tools,  # Pass tool schemas
            )

            # 3. Track cumulative token usage
            self._token_usage["input"] += response.usage.input_tokens
            self._token_usage["output"] += response.usage.output_tokens

            # 4. Check total budget (safety)
            if self._token_usage["output"] > self.max_tokens:
                raise RuntimeError(
                    f"Agent exceeded token budget: {self._token_usage['output']} > {self.max_tokens}"
                )

            # 5. Add assistant message to conversation
            messages.append({"role": "assistant", "content": response.content})

            # 6. Handle response based on stop_reason
            if response.stop_reason == "tool_use":
                # Process tool calls...
            elif response.stop_reason == "max_tokens":
                # Handle truncation...
            elif response.stop_reason == "end_turn":
                # Agent finished without tool use (error)
                raise RuntimeError("Agent ended conversation without submitting HTML")

    except Exception as e:
        log.error("agent.loop.error", error=str(e), iteration=iteration, tokens=self._token_usage)
        raise
```

**Loop Principles:**
- Start conversation with structured context (JSON format)
- Maintain conversation history in `messages` list
- Set both per-request (`max_tokens=8192`) and total budget limits
- Always append assistant response to conversation before processing tools
- Handle all possible `stop_reason` values explicitly
- Comprehensive logging at each iteration

#### Tool Use Handling

```python
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
                log.info("agent.loop.complete", iterations=iteration, tokens=self._token_usage)
                return e.html_content

    # Add tool results back to conversation
    messages.append({"role": "user", "content": tool_results})
```

**Tool Use Principles:**
- Iterate through all content blocks (may have multiple tool calls)
- Execute each tool call via `_handle_tool_call()`
- Collect results with proper structure: `type`, `tool_use_id`, `content`
- Add results as a user message (Claude expects tool results from user)
- Handle special termination conditions (e.g., `submit_html` tool)

#### Max Tokens Handling

```python
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
                return e.html_content

    # If there were tool calls, add results to conversation
    if has_tool_calls:
        messages.append({"role": "user", "content": tool_results})
    # Otherwise just continue (pure text was truncated, agent will retry)
```

**Truncation Handling Principles:**
- When `max_tokens` is hit, response may be truncated
- Tool calls can still be complete even if text is cut off
- Process any complete tool calls and continue
- If no tool calls, just continue loop (agent will retry)

#### Tool Execution

```python
def _handle_tool_call(self, tool_use: Any) -> str:
    """Handle a single tool call.

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
        raise AgentTerminated(content)  # Special exception to terminate loop

    else:
        return f"Unknown tool: {tool_name}"
```

**Tool Execution Principles:**
- Extract `tool_use.name` and `tool_use.input`
- Validate inputs exist (handle truncation gracefully)
- Delegate actual execution to runtime/backend
- Return errors as strings (don't crash the loop)
- Use exceptions for control flow (e.g., `AgentTerminated`)
- Log all tool calls and results

#### Custom Exception for Termination

```python
class AgentTerminated(Exception):
    """Raised when the agent calls submit_html."""

    def __init__(self, html_content: str):
        self.html_content = html_content
        super().__init__("Agent submitted HTML")
```

**Pattern:**
- Use custom exceptions to signal special conditions
- Carry data through the exception (e.g., HTML content)
- Catch in the loop and handle appropriately

### 3. Tool Execution Runtime (`src/cataloger/container/runtime.py`)

The `ContainerRuntime` class executes Python code in a persistent Docker container:

```python
class ContainerRuntime:
    """Manages a single container for executing Python code.

    This maintains a PERSISTENT Python interpreter process that stays alive
    across multiple execute() calls, enabling true stateful sessions like
    IPython or Jupyter.

    Key difference from naive approach:
    - NOT: docker exec python -c "code" (new process each time, no state)
    - YES: Single python -i process, send code via stdin, read from stdout
    """

    def __init__(
        self,
        container: Container,
        db_connection_string: str | None = None,
        s3_config: dict[str, Any] | None = None,
    ):
        self.container = container
        self.db_connection_string = db_connection_string
        self.s3_config = s3_config or {}
        self._code_history: list[str] = []
        self._output_history: list[str] = []
        self._session_id = str(uuid.uuid4())[:8]

        # Create a unique marker for detecting end of output
        self._output_marker = f"__CATALOGER_OUTPUT_END_{self._session_id}__"

        # Start persistent Python interpreter
        self._start_interpreter()
```

#### Persistent Interpreter Pattern

The runtime creates a long-running Python process that:
1. Reads code from `/tmp/code_input.py`
2. Executes it in a persistent global namespace
3. Writes output to `/tmp/code_output.txt` with a marker
4. Loops back to wait for next code

This enables **stateful execution** where variables, imports, and functions persist across tool calls.

```python
def _start_interpreter(self) -> None:
    """Start a persistent Python interpreter in the container."""

    interpreter_script = textwrap.dedent(
        f'''
        import sys, os, traceback
        from io import StringIO

        # Set environment variables
        os.environ["DB_CONNECTION_STRING"] = {self.db_connection_string!r} or ""
        os.environ["AWS_ACCESS_KEY_ID"] = {self.s3_config.get("aws_access_key_id", "")!r}
        # ... other env vars

        # Global namespace for persistent state
        _globals = {{"__name__": "__main__"}}

        # Interpreter loop
        while True:
            # Wait for code file
            if not os.path.exists("/tmp/code_input.py"):
                import time
                time.sleep(0.1)
                continue

            # Read code
            with open("/tmp/code_input.py", "r") as f:
                code = f.read()
            os.remove("/tmp/code_input.py")

            # Capture output
            output_buffer = StringIO()
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = sys.stderr = output_buffer

            try:
                exec(code, _globals)  # Execute in persistent globals
            except Exception:
                traceback.print_exc()
            finally:
                sys.stdout, sys.stderr = old_stdout, old_stderr

            # Write output with marker
            output = output_buffer.getvalue()
            with open("/tmp/code_output.txt", "w") as f:
                f.write(output)
                f.write("\\n{self._output_marker}\\n")
        '''
    )

    # Write and start interpreter script
    create_script_cmd = f'cat > /tmp/interpreter.py << \'EOF\'\n{interpreter_script}\nEOF'
    self.container.exec_run(cmd=["sh", "-c", create_script_cmd], user="agent")

    start_cmd = "python -u /tmp/interpreter.py > /tmp/interpreter.log 2>&1 &"
    self.container.exec_run(cmd=["sh", "-c", start_cmd], user="agent", detach=True)

    import time
    time.sleep(0.5)  # Give interpreter time to start
```

#### Code Execution

```python
def execute(self, code: str, timeout: int = 60) -> str:
    """Execute Python code in the persistent interpreter.

    Returns:
        Combined stdout/stderr output as a single string

    Raises:
        ExecutionError: If execution fails or times out
    """
    # Track code history
    self._code_history.append(code)

    # Clean up previous output
    self.container.exec_run(cmd=["sh", "-c", "rm -f /tmp/code_output.txt"], user="agent")

    # Write code to input file
    write_code_cmd = f"cat > /tmp/code_input.py << 'EOF'\n{code}\nEOF"
    self.container.exec_run(cmd=["sh", "-c", write_code_cmd], user="agent")

    # Wait for output file (with timeout)
    import time
    start_time = time.time()
    while time.time() - start_time < timeout:
        result = self.container.exec_run(
            cmd=["sh", "-c", "test -f /tmp/code_output.txt && echo exists"],
            user="agent",
        )
        if result.output.decode().strip() == "exists":
            break
        time.sleep(0.1)
    else:
        raise ExecutionError(f"Code execution timeout after {timeout}s")

    # Read output
    result = self.container.exec_run(cmd=["cat", "/tmp/code_output.txt"], user="agent")
    output = result.output.decode("utf-8")

    # Remove marker and track output
    output = output.replace(f"\n{self._output_marker}\n", "")
    cleaned_output = output.rstrip()
    self._output_history.append(cleaned_output)

    return cleaned_output
```

**Runtime Principles:**
- Maintain code and output history for debugging/replay
- Use file-based communication (simpler than sockets)
- Poll for output file with timeout
- Return combined stdout/stderr as single string
- Raise exceptions on timeout or execution errors

### 4. Message Flow Protocol

The conversation follows this pattern:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. User message with context                               │
│    {"role": "user", "content": "Context:\n{json}\n..."}    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Assistant response with tool_use blocks                 │
│    {"role": "assistant", "content": [                      │
│       {"type": "text", "text": "I'll check the database"},│
│       {"type": "tool_use", "id": "...", "name": "...",    │
│        "input": {...}}                                     │
│    ]}                                                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Execute tools and collect results                       │
│    - Extract tool_use.name and tool_use.input             │
│    - Execute actual tool (delegate to runtime)             │
│    - Collect result string                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. User message with tool_result blocks                    │
│    {"role": "user", "content": [                           │
│       {"type": "tool_result", "tool_use_id": "...",       │
│        "content": "output from execution"}                 │
│    ]}                                                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
                    (Loop continues)
```

### 5. Safety and Error Handling

Multiple layers of protection:

#### Token Budget Limits
```python
# Per-request limit
response = client.messages.create(
    max_tokens=8192,  # Single response limit
    ...
)

# Total budget check
if self._token_usage["output"] > self.max_tokens:
    raise RuntimeError(f"Agent exceeded token budget: {self._token_usage['output']} > {self.max_tokens}")
```

#### Iteration Limits
```python
max_iterations = 50  # Prevents infinite loops

while iteration < max_iterations:
    iteration += 1
    ...

raise RuntimeError(f"Agent exceeded max iterations: {max_iterations}")
```

#### Execution Timeouts
```python
def execute(self, code: str, timeout: int = 60) -> str:
    """Execute with timeout to prevent hanging."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Check for output...
    else:
        raise ExecutionError(f"Code execution timeout after {timeout}s")
```

#### Truncation Handling
```python
# Check if required fields exist (may be truncated)
if "code" not in tool_input:
    return "Error: execute_python call was truncated. Please retry with complete code."
```

#### Error Return (Don't Crash)
```python
try:
    output = self.runtime.execute(code)
    return output
except ExecutionError as e:
    # Return error as string, don't crash the loop
    return f"Execution error:\n{str(e)}"
```

### 6. LLM Client Setup

```python
import anthropic
import os

# Initialize client
llm_api_key = os.getenv("LLM_API_KEY")
if not llm_api_key:
    raise ValueError("Missing LLM_API_KEY environment variable")

anthropic_client = anthropic.Anthropic(api_key=llm_api_key)

# Get model name
model_name = os.getenv("MODEL_NAME", "claude-haiku-4-5")

# Create agent
agent = AgentLoop(
    client=anthropic_client,
    runtime=container_runtime,
    model=model_name,
    max_tokens=100_000,
    temperature=0.0,
)

# Run agent
result = agent.run(
    system_prompt=prompt_text,
    context={"tables": ["users", "orders"]},
)
```

### 7. Testing

Test tool schemas are correctly structured:

```python
def test_tool_schemas():
    """Test that tool schemas are correctly defined."""
    tools = get_tool_schemas()

    assert len(tools) == 2

    # Validate execute_python schema
    exec_tool = next(t for t in tools if t["name"] == "execute_python")
    assert "code" in exec_tool["input_schema"]["properties"]
    assert "code" in exec_tool["input_schema"]["required"]
    assert exec_tool["input_schema"]["type"] == "object"

    # Validate submit_html schema
    submit_tool = next(t for t in tools if t["name"] == "submit_html")
    assert "content" in submit_tool["input_schema"]["properties"]
    assert "content" in submit_tool["input_schema"]["required"]
```

## Key Design Decisions

### 1. Minimalist Tool Set
Following the "Armin Ronacher Tools" pattern, provide only essential tools:
- **execute_python**: General-purpose computation/exploration tool
- **submit_html**: Terminal action that ends the loop

This reduces complexity and forces the LLM to be creative with limited tools.

### 2. Persistent State
The Python interpreter maintains state across tool calls, enabling:
- Variable reuse (no need to re-import libraries)
- Incremental exploration (build on previous queries)
- Natural workflow (like Jupyter notebooks)

### 3. Stateful Container Runtime
Using Docker provides:
- Isolation (safe code execution)
- Reproducibility (consistent environment)
- Resource limits (CPU, memory controls)
- Clean reset (destroy and recreate containers)

### 4. Error Resilience
The system continues operation despite errors:
- Execution errors returned as strings (don't crash loop)
- Truncated tool calls handled gracefully
- Timeout protection at multiple levels

### 5. Comprehensive Logging
Structured logging throughout:
- Every iteration logged with token counts
- Every tool call logged with input/output sizes
- Errors logged with full context

### 6. Token Budget Management
Two-level token control:
- Per-request limit (8192) prevents runaway generations
- Total budget (100,000) prevents excessive costs
- Cumulative tracking across all iterations

## Dependencies

```toml
[dependencies]
anthropic = ">=0.39.0"  # Claude API with tool support
docker = ">=7.1.0"      # Container runtime
structlog = ">=24.4.0"  # Structured logging
```

## Configuration

Environment variables:
- `LLM_API_KEY`: Anthropic API key (required)
- `MODEL_NAME`: Claude model to use (default: "claude-haiku-4-5")
- `DB_CONNECTION_STRING`: Database connection (passed to container)
- `AWS_*`: AWS credentials for S3 access (passed to container)

## Usage Example

```python
import anthropic
from cataloger.agent.loop import AgentLoop
from cataloger.container.runtime import ContainerRuntime

# Setup
client = anthropic.Anthropic(api_key=os.getenv("LLM_API_KEY"))
container = docker_client.containers.run(
    image="cataloger-agent",
    detach=True,
    environment={"DB_CONNECTION_STRING": "..."},
)
runtime = ContainerRuntime(container)

# Create agent
agent = AgentLoop(
    client=client,
    runtime=runtime,
    model="claude-sonnet-4-0",
    max_tokens=100_000,
)

# Run
system_prompt = """You are a database analyst.
Explore the tables and create an HTML report."""

result = agent.run(
    system_prompt=system_prompt,
    context={"tables": ["users", "orders", "products"]},
)

# result is the HTML submitted by the agent
print(result)
```

## Best Practices Summary

1. **Tool Design**
   - Keep tool count minimal
   - Write detailed descriptions for the LLM
   - Include usage hints in descriptions
   - Use JSON Schema for input validation

2. **Loop Architecture**
   - Track all token usage cumulatively
   - Set both per-request and total budgets
   - Handle all stop_reason values explicitly
   - Log every iteration comprehensively

3. **Tool Execution**
   - Validate inputs (handle truncation)
   - Return errors as strings (don't crash)
   - Use exceptions for control flow
   - Maintain execution history

4. **Safety**
   - Multiple timeout layers
   - Iteration limits
   - Token budgets
   - Container isolation

5. **Error Handling**
   - Graceful degradation
   - Informative error messages
   - Comprehensive logging
   - Recovery mechanisms

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                        AgentLoop                             │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 1. Initialize messages with context                    │  │
│  │ 2. Loop:                                               │  │
│  │    a. Call Claude API with tools                       │  │
│  │    b. Track token usage                                │  │
│  │    c. Handle stop_reason:                              │  │
│  │       - tool_use: Execute tools, add results           │  │
│  │       - max_tokens: Handle truncation                  │  │
│  │       - end_turn: Error (shouldn't happen)             │  │
│  │    d. Check budget limits                              │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                          ↓
                    Tool Execution
                          ↓
┌──────────────────────────────────────────────────────────────┐
│                   ContainerRuntime                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ Persistent Python Interpreter                          │  │
│  │ - Read code from /tmp/code_input.py                    │  │
│  │ - Execute in global namespace                          │  │
│  │ - Write output to /tmp/code_output.txt                 │  │
│  │ - Loop back                                             │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Quick Reference Checklist

When implementing tool calling in a new project, ensure you have:

- [ ] Tool schemas defined in JSON Schema format
- [ ] Tool descriptions that explain behavior to LLM
- [ ] Agent loop with conversation history
- [ ] Per-request token limits
- [ ] Total token budget tracking
- [ ] Iteration limits
- [ ] All stop_reason cases handled
- [ ] Tool execution delegation to runtime
- [ ] Error handling (return strings, don't crash)
- [ ] Truncation handling
- [ ] Execution timeouts
- [ ] Comprehensive logging
- [ ] Token usage tracking
- [ ] Custom exceptions for control flow
- [ ] Tests for tool schemas
- [ ] Environment-based configuration

---

*This document describes the implementation in the cataloger project (commit: e56d632). Refer to actual source code for latest details.*
