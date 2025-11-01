# Implementation Gaps: Aligning with Armin's Code MCP Pattern

After reviewing [Armin Ronacher's blog post](https://lucumr.pocoo.org/2025/8/18/code-mcps/) on code-based MCPs, here are the key gaps in our current implementation:

## Critical Issue: State Does NOT Actually Persist

**Problem**: Our current `ContainerRuntime.execute()` runs `python -c "code"` for each call, which spawns a NEW Python process each time. This means:
- Variables defined in one execute() call are lost in the next
- No persistent Python session across calls
- Agent cannot build up state incrementally

**Current implementation** (src/cataloger/container/runtime.py:96-97):
```python
exit_code, output = self.container.exec_run(
    cmd=["python", "-c", wrapper],  # NEW PROCESS EACH TIME!
```

**What we claimed**: "Each container maintains a persistent Python process across multiple execute() calls, simulating an IPython-like session where state persists."

**Reality**: State does NOT persist. Each call is isolated.

## What Armin's Approach Requires

### 1. Single Persistent Python Process

Instead of `python -c` per call, we need:
- Start a single Python REPL/interpreter when container is acquired
- Keep it running throughout the agent's lifetime
- Send code to it via stdin
- Read output from stdout/stderr
- The process maintains all state (variables, imports, etc.)

Example pattern (like pexpect-mcp):
```python
# Container startup
self.python_proc = subprocess.Popen(
    ["python", "-u", "-i"],  # -i for interactive mode
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=0,  # Unbuffered
)

# Each execute() call
def execute(self, code):
    self.python_proc.stdin.write(code + "\n")
    self.python_proc.stdin.flush()
    # Read output until prompt/marker
    return self._read_output()
```

### 2. Simpler Code Execution

**Current**: Complex wrapper trying to:
- Capture output with StringIO
- Auto-print last expression (like IPython)
- Handle errors specially

**Armin's approach**: Just exec() the code directly
- If agent wants output, they use print()
- If agent wants value displayed, they print it
- Simpler, more predictable

### 3. Code Persistence / Script Extraction

**Missing**: We don't save the sequence of executed code

**Should add**:
- Log all executed code for audit trail
- Provide mechanism to extract session as standalone script
- Enable replay/debugging

Example:
```python
class ContainerRuntime:
    def __init__(self, ...):
        self._code_history = []

    def execute(self, code):
        self._code_history.append(code)
        # ... execute ...

    def get_session_script(self):
        return "\n\n".join(self._code_history)
```

### 4. Remove Over-Engineering

**Current issues**:
- Complex output capture with StringIO
- Trying to guess if last line is expression
- Complicated error handling in wrapper

**Better approach**:
- Simple exec() in persistent interpreter
- Let agent handle all output via print()
- Natural Python error messages

## Implementation Changes Needed

### High Priority

1. **Refactor ContainerRuntime** to maintain persistent Python process
   - Use subprocess.Popen with pipes
   - Communicate via stdin/stdout
   - Implement proper output reading (until prompt marker)

2. **Simplify code execution**
   - Remove complex wrapper
   - Direct exec() in persistent globals()
   - Agent uses print() for output

3. **Add code history tracking**
   - Save all executed code
   - Expose via get_session_script()

### Medium Priority

4. **Improve error output**
   - Let Python's natural tracebacks through
   - Don't exit on error (return error as output)
   - Agent can inspect and retry

5. **Add session management**
   - Ability to reset interpreter state
   - Without killing container (just restart Python process)

6. **Consider MCP protocol** (optional)
   - Current: We call Claude API directly
   - Alternative: Expose Cataloger as MCP server
   - Would allow integration with Claude Desktop, etc.

### Low Priority

7. **Script replay testing**
   - Extract session script
   - Run it standalone to verify results
   - Useful for debugging and optimization

## Code Examples

### Before (Current - BROKEN STATE PERSISTENCE)

```python
# Call 1
runtime.execute("x = 42")  # Runs: python -c "x = 42"

# Call 2
runtime.execute("print(x)")  # Runs: python -c "print(x)"  --> ERROR! x not defined
```

### After (True State Persistence)

```python
# Container startup creates persistent interpreter
runtime = ContainerRuntime(container)  # Starts: python -i

# Call 1
runtime.execute("x = 42")  # Sends to interpreter: "x = 42\n"

# Call 2
runtime.execute("print(x)")  # Sends to interpreter: "print(x)\n"  --> Works! Prints "42"
```

## Testing Impact

Current tests will need updates:
- `test_state_persists()` currently PASSES but doesn't actually test persistence
- Need to verify state truly persists across multiple execute() calls
- Add tests for session script extraction

## Architecture Impact

This is a significant change:
- More complex process management (keep Python alive)
- Need proper cleanup (kill Python process on container release)
- Output reading becomes more complex (need to detect when execution completes)
- But: matches Armin's proven pattern

## Benefits of Fixing This

1. **True agent state**: Agent can build complex analysis incrementally
2. **Better matches expectations**: "IPython-like session" becomes reality
3. **Script extraction**: Generated analysis becomes reusable automation
4. **Follows proven pattern**: Armin's pexpect-mcp demonstrates this works

## Next Steps

1. Decide if we want to fix this for MVP or document limitation
2. If fixing: Implement persistent Python process pattern
3. Update tests to verify true state persistence
4. Update documentation to match actual behavior
