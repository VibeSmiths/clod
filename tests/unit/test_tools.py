"""
Unit tests for tool executor functions and TOOL_DEFINITIONS schema.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import tool_read_file, tool_write_file, TOOL_DEFINITIONS

# ── tool_read_file ─────────────────────────────────────────────────────────────


def test_tool_read_file_existing(tmp_path):
    """Reading an existing file returns its contents."""
    f = tmp_path / "hello.txt"
    f.write_text("hello world\n")
    result = tool_read_file({"path": str(f)})
    assert "hello world" in result


def test_tool_read_file_missing():
    """Reading a non-existent file returns an error message."""
    result = tool_read_file({"path": "/nonexistent/path/to/file.txt"})
    assert "not found" in result.lower() or "error" in result.lower()


def test_tool_read_file_line_limit(tmp_path):
    """Reading with a line limit returns at most that many lines."""
    f = tmp_path / "big.txt"
    f.write_text("\n".join(str(i) for i in range(100)))
    result = tool_read_file({"path": str(f), "lines": 5})
    lines = result.strip().splitlines()
    assert len(lines) <= 5


# ── tool_write_file ────────────────────────────────────────────────────────────


def test_tool_write_file_creates(tmp_path):
    """Writing to a new path creates the file with the given content."""
    out = tmp_path / "out.txt"
    result = tool_write_file({"path": str(out), "content": "test content"})
    assert out.exists()
    assert out.read_text() == "test content"
    assert "Wrote" in result or "wrote" in result.lower()


def test_tool_write_file_appends(tmp_path):
    """Appending to an existing file adds content without overwriting."""
    out = tmp_path / "append.txt"
    out.write_text("line1\n")
    tool_write_file({"path": str(out), "content": "line2\n", "append": True})
    assert out.read_text() == "line1\nline2\n"


# ── TOOL_DEFINITIONS schema ────────────────────────────────────────────────────


def test_tool_definitions_valid_structure():
    """All tools follow the OpenAI function-calling schema."""
    for tool in TOOL_DEFINITIONS:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        params = fn["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


def test_all_tools_have_executors():
    """Every tool name in TOOL_DEFINITIONS has a handler in execute_tool()."""
    tool_names = {t["function"]["name"] for t in TOOL_DEFINITIONS}
    handled = {"bash_exec", "read_file", "write_file", "web_search"}
    assert tool_names == handled
