"""Tool schemas for agent execution.

Following Armin Ronacher's "Tools" pattern, we provide just two tools:
- execute_python(code): Run Python code in the container
- submit_html(content): Submit the final HTML report
"""

from typing import Any

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
