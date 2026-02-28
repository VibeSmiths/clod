"""
Tests for tool executor functions:
  tool_bash_exec, tool_web_search, execute_tool
Also covers tool_read_file and tool_write_file dispatch paths.
"""

import sys
import pathlib
import subprocess

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import requests
import responses as resp_lib

import clod

# ── Mock console ──────────────────────────────────────────────────────────────


class _MockConsole:
    """Minimal console stub for tool tests."""

    def __init__(self, input_response="n"):
        self._input_response = input_response

    def print(self, *args, **kwargs):
        pass

    def input(self, *args, **kwargs):
        return self._input_response

    def status(self, *args, **kwargs):
        import contextlib

        return contextlib.nullcontext()


# ── tool_bash_exec ────────────────────────────────────────────────────────────


def test_tool_bash_exec_decline(fake_console, mock_cfg):
    """When user inputs 'n', command is not run and a decline message is returned."""
    # fake_console.input returns "" by default which is not 'y', so this declines
    result = clod.tool_bash_exec({"command": "echo should_not_run"}, fake_console)
    assert "declined" in result.lower()


def test_tool_bash_exec_decline_explicit_n():
    """Explicit 'n' input declines execution."""
    console = _MockConsole(input_response="n")
    result = clod.tool_bash_exec({"command": "echo secret"}, console)
    assert "declined" in result.lower()


def test_tool_bash_exec_accept_runs_command():
    """When user accepts with 'y', the command is executed and stdout returned."""
    console = _MockConsole(input_response="y")
    result = clod.tool_bash_exec({"command": "echo hello_world"}, console)
    assert "hello_world" in result


def test_tool_bash_exec_accept_yes():
    """'yes' is also a valid confirmation."""
    console = _MockConsole(input_response="yes")
    result = clod.tool_bash_exec({"command": "echo confirmed"}, console)
    assert "confirmed" in result


def test_tool_bash_exec_no_output():
    """Command with no stdout/stderr returns '(no output)'."""
    console = _MockConsole(input_response="y")
    # A no-op command on all platforms
    result = clod.tool_bash_exec({"command": 'python -c "pass"'}, console)
    assert "(no output)" in result or result == "(no output)"


def test_tool_bash_exec_timeout(monkeypatch):
    """TimeoutExpired returns a timeout message."""
    console = _MockConsole(input_response="y")

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("sleep", 1)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    result = clod.tool_bash_exec({"command": "sleep 9999", "timeout": 1}, console)
    assert "timed out" in result.lower()


def test_tool_bash_exec_uses_timeout_from_args(monkeypatch):
    """Custom timeout from args is passed to subprocess.run."""
    console = _MockConsole(input_response="y")
    captured = {}

    def fake_run(*args, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        import subprocess as sp

        r = sp.CompletedProcess(args=args, returncode=0, stdout="done\n", stderr="")
        return r

    monkeypatch.setattr(subprocess, "run", fake_run)
    clod.tool_bash_exec({"command": "echo x", "timeout": 42}, console)
    assert captured["timeout"] == 42


# ── tool_web_search ───────────────────────────────────────────────────────────


@resp_lib.activate
def test_tool_web_search_success(mock_cfg):
    """Returns formatted string containing title and URL."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8080/search",
        json={
            "results": [
                {"title": "T", "url": "http://x.com", "content": "snippet text"},
            ]
        },
    )
    result = clod.tool_web_search({"query": "test", "count": 1}, mock_cfg["searxng_url"])
    assert "T" in result
    assert "http://x.com" in result
    assert "snippet text" in result


@resp_lib.activate
def test_tool_web_search_empty_results(mock_cfg):
    """Empty results list returns 'No results found.'"""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8080/search",
        json={"results": []},
    )
    result = clod.tool_web_search({"query": "nothing", "count": 5}, mock_cfg["searxng_url"])
    assert "No results found" in result


@resp_lib.activate
def test_tool_web_search_http_error(mock_cfg):
    """HTTP error returns a 'Search error' string."""
    resp_lib.add(resp_lib.GET, "http://localhost:8080/search", status=500)
    result = clod.tool_web_search({"query": "boom", "count": 3}, mock_cfg["searxng_url"])
    assert "error" in result.lower()


@resp_lib.activate
def test_tool_web_search_connection_error(mock_cfg):
    """ConnectionError returns a 'Search error' string."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8080/search",
        body=requests.exceptions.ConnectionError(),
    )
    result = clod.tool_web_search({"query": "offline", "count": 3}, mock_cfg["searxng_url"])
    assert "error" in result.lower()


@resp_lib.activate
def test_tool_web_search_default_count(mock_cfg):
    """Default count of 5 results when count not specified."""
    many_results = [
        {"title": f"R{i}", "url": f"http://example.com/{i}", "content": ""} for i in range(10)
    ]
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8080/search",
        json={"results": many_results},
    )
    result = clod.tool_web_search({"query": "many"}, mock_cfg["searxng_url"])
    # Only 5 results should appear (default count=5)
    count = result.count("http://example.com/")
    assert count == 5


@resp_lib.activate
def test_tool_web_search_no_content_field(mock_cfg):
    """Result without 'content' key is handled without KeyError."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8080/search",
        json={"results": [{"title": "No Content", "url": "http://nc.com"}]},
    )
    result = clod.tool_web_search({"query": "x", "count": 1}, mock_cfg["searxng_url"])
    assert "No Content" in result


# ── execute_tool dispatch ─────────────────────────────────────────────────────


def test_execute_tool_read_file(tmp_path, fake_console, mock_cfg):
    """execute_tool dispatches 'read_file' to tool_read_file."""
    f = tmp_path / "hello.txt"
    f.write_text("file content")
    result = clod.execute_tool("read_file", {"path": str(f)}, fake_console, mock_cfg)
    assert "file content" in result


def test_execute_tool_write_file(tmp_path, fake_console, mock_cfg):
    """execute_tool dispatches 'write_file' to tool_write_file."""
    f = tmp_path / "out.txt"
    result = clod.execute_tool(
        "write_file", {"path": str(f), "content": "written"}, fake_console, mock_cfg
    )
    assert "Wrote" in result or "wrote" in result.lower()
    assert f.read_text() == "written"


@resp_lib.activate
def test_execute_tool_web_search(fake_console, mock_cfg):
    """execute_tool dispatches 'web_search' to tool_web_search."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8080/search",
        json={"results": [{"title": "Found", "url": "http://f.com", "content": "detail"}]},
    )
    result = clod.execute_tool(
        "web_search", {"query": "found it", "count": 1}, fake_console, mock_cfg
    )
    assert "Found" in result


def test_execute_tool_bash_exec_decline(fake_console, mock_cfg):
    """execute_tool dispatches 'bash_exec'; fake_console declines (input='')."""
    result = clod.execute_tool("bash_exec", {"command": "echo nope"}, fake_console, mock_cfg)
    assert "declined" in result.lower()


def test_execute_tool_unknown(fake_console, mock_cfg):
    """Unknown tool name returns 'Unknown tool: <name>'."""
    result = clod.execute_tool("nonexistent_tool", {}, fake_console, mock_cfg)
    assert "Unknown tool" in result
    assert "nonexistent_tool" in result
