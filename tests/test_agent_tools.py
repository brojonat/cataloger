"""Tests for agent tool schemas."""

from cataloger.agent.tools import get_tool_schemas


def test_tool_schemas():
    """Test that tool schemas are correctly defined."""
    tools = get_tool_schemas()

    assert len(tools) == 2

    # Check execute_python tool
    exec_tool = next(t for t in tools if t["name"] == "execute_python")
    assert exec_tool["description"]
    assert "code" in exec_tool["input_schema"]["properties"]
    assert "code" in exec_tool["input_schema"]["required"]

    # Check submit_html tool
    submit_tool = next(t for t in tools if t["name"] == "submit_html")
    assert submit_tool["description"]
    assert "content" in submit_tool["input_schema"]["properties"]
    assert "content" in submit_tool["input_schema"]["required"]
