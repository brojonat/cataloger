import io
import os
import sys
import tempfile
import textwrap
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import docker
from docker.models.containers import Container


class ExecutionError(Exception):
    """Raised when code execution fails."""

    pass


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

    def _start_interpreter(self) -> None:
        """Start a persistent Python interpreter in the container.

        This creates a socket-based communication channel so we can send
        code and receive output from a long-running Python process.
        """
        # Create a Python script that:
        # 1. Starts an interpreter loop
        # 2. Reads code from a file
        # 3. Executes it
        # 4. Writes output to another file
        # 5. Prints a marker when done

        interpreter_script = textwrap.dedent(
            f'''
            import sys
            import os
            import traceback
            from io import StringIO

            # Set environment variables
            os.environ["DB_CONNECTION_STRING"] = {self.db_connection_string!r} or ""
            os.environ["AWS_ACCESS_KEY_ID"] = {self.s3_config.get("aws_access_key_id", "")!r}
            os.environ["AWS_SECRET_ACCESS_KEY"] = {self.s3_config.get("aws_secret_access_key", "")!r}
            os.environ["AWS_DEFAULT_REGION"] = {self.s3_config.get("region", "us-east-1")!r}
            os.environ["S3_BUCKET"] = {self.s3_config.get("bucket", "")!r}
            os.environ["S3_ENDPOINT_URL"] = {self.s3_config.get("endpoint_url", "")!r}

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
                error_occurred = False

                # Redirect stdout/stderr
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = output_buffer
                sys.stderr = output_buffer

                try:
                    # Execute code in persistent globals
                    exec(code, _globals)
                except Exception:
                    error_occurred = True
                    traceback.print_exc()
                finally:
                    # Restore stdout/stderr
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr

                # Write output
                output = output_buffer.getvalue()
                with open("/tmp/code_output.txt", "w") as f:
                    f.write(output)
                    f.write("\\n{self._output_marker}\\n")
                    if error_occurred:
                        f.write("ERROR\\n")
            '''
        )

        # Write interpreter script to container
        create_script_cmd = f'cat > /tmp/interpreter.py << \'EOF\'\n{interpreter_script}\nEOF'
        self.container.exec_run(cmd=["sh", "-c", create_script_cmd], user="agent")

        # Start interpreter in background
        # We use 'sh -c' with '&' to truly background it
        start_cmd = "python -u /tmp/interpreter.py > /tmp/interpreter.log 2>&1 &"
        self.container.exec_run(cmd=["sh", "-c", start_cmd], user="agent", detach=True)

        # Give it a moment to start
        import time

        time.sleep(0.5)

    def execute(self, code: str, timeout: int = 60) -> str:
        """Execute Python code in the persistent interpreter.

        The interpreter maintains state across calls, so variables,
        imports, and function definitions persist.

        Args:
            code: Python code to execute
            timeout: Maximum execution time in seconds

        Returns:
            Combined stdout/stderr output as a single string

        Raises:
            ExecutionError: If execution fails or times out
        """
        # Track code history
        self._code_history.append(code)

        # Clean up any previous output file
        self.container.exec_run(cmd=["sh", "-c", "rm -f /tmp/code_output.txt"], user="agent")

        # Write code to input file
        write_code_cmd = f"cat > /tmp/code_input.py << 'EOF'\n{code}\nEOF"
        self.container.exec_run(cmd=["sh", "-c", write_code_cmd], user="agent")

        # Wait for output file to appear (with timeout)
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
        result = self.container.exec_run(
            cmd=["cat", "/tmp/code_output.txt"], user="agent"
        )
        output = result.output.decode("utf-8")

        # Check for error marker
        if output.endswith("ERROR\n"):
            # Remove marker and ERROR line
            output = output[: -len("ERROR\n")]
            # Remove the output marker line
            output = output.replace(f"\n{self._output_marker}\n", "")
            # Track the error output
            self._output_history.append(output.rstrip())
            raise ExecutionError(f"Code execution failed:\n{output}")

        # Remove the output marker
        output = output.replace(f"\n{self._output_marker}\n", "")

        # Track the output
        cleaned_output = output.rstrip()
        self._output_history.append(cleaned_output)

        return cleaned_output

    def get_code_history(self) -> list[str]:
        """Return the list of all code snippets executed in this session."""
        return self._code_history.copy()

    def get_session_script(self) -> str:
        """Return the complete session as a standalone Python script.

        This concatenates all executed code blocks with their outputs
        (as comments), making it easy to replay the session or turn it
        into automation while preserving what the agent observed.
        """
        script_parts = []

        for i, (code, output) in enumerate(zip(self._code_history, self._output_history)):
            # Add code block
            script_parts.append(f"# === Code Block {i + 1} ===")
            script_parts.append(code)

            # Always add output section for clarity
            script_parts.append("")
            script_parts.append(f"# --- Output {i + 1} ---")
            if output:
                # Comment each line of output
                for line in output.split("\n"):
                    script_parts.append(f"# {line}")
            else:
                script_parts.append("# (no output)")

            script_parts.append("")  # Blank line between blocks

        return "\n".join(script_parts)

    def reset(self) -> None:
        """Reset the Python interpreter state.

        This kills the current interpreter, clearing all variables and imports.
        Note: Does NOT start a new interpreter - that will happen when the
        container is reused with a new ContainerRuntime instance.
        """
        # Kill the old interpreter
        self.container.exec_run(
            cmd=["sh", "-c", "pkill -f 'python -u /tmp/interpreter.py'"], user="agent"
        )

        # Clear code and output history
        self._code_history = []
        self._output_history = []

        # Clean up temp files to prevent confusion
        self.container.exec_run(
            cmd=["sh", "-c", "rm -f /tmp/code_input.py /tmp/code_output.txt /tmp/interpreter.py"],
            user="agent"
        )

    def cleanup(self) -> None:
        """Stop and remove the container."""
        # Kill interpreter
        try:
            self.container.exec_run(
                cmd=["sh", "-c", "pkill -f 'python -u /tmp/interpreter.py'"],
                user="agent",
            )
        except Exception:
            pass

        # Stop and remove container
        try:
            self.container.stop(timeout=5)
            self.container.remove()
        except docker.errors.APIError:
            # Container may already be stopped
            pass
