"""
Tests for streaming backend functions:
  stream_ollama, stream_openai_compat, stream_and_render
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import requests
import responses as resp_lib

import clod

# ── stream_ollama ─────────────────────────────────────────────────────────────


@resp_lib.activate
def test_stream_ollama_tokens(mock_cfg):
    """Normal two-chunk stream yields two token events followed by done."""
    body = (
        b'{"message": {"content": "hello "}, "done": false}\n'
        b'{"message": {"content": "world"}, "done": true}\n'
    )
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/chat", body=body)

    events = list(clod.stream_ollama([{"role": "user", "content": "hi"}], "m", mock_cfg))
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert tokens == ["hello ", "world"]


@resp_lib.activate
def test_stream_ollama_done_event(mock_cfg):
    """Last event should be 'done' when no tool calls present."""
    body = b'{"message": {"content": "ok"}, "done": true}\n'
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/chat", body=body)

    events = list(clod.stream_ollama([{"role": "user", "content": "hi"}], "m", mock_cfg))
    types = [e["type"] for e in events]
    assert "done" in types
    done_events = [e for e in events if e["type"] == "done"]
    assert done_events[0]["message"]["content"] == "ok"


@resp_lib.activate
def test_stream_ollama_connection_error(mock_cfg):
    """ConnectionError yields a single error event."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        body=requests.exceptions.ConnectionError(),
    )

    events = list(clod.stream_ollama([{"role": "user", "content": "hi"}], "m", mock_cfg))
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "Cannot connect" in events[0]["text"]


@resp_lib.activate
def test_stream_ollama_http_error(mock_cfg):
    """HTTP 500 yields a single error event."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        status=500,
        body=b"Internal Server Error",
    )

    events = list(clod.stream_ollama([{"role": "user", "content": "hi"}], "m", mock_cfg))
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "500" in events[0]["text"]


@resp_lib.activate
def test_stream_ollama_tool_calls_in_final_message(mock_cfg):
    """Tool calls in the final done chunk are yielded as tool_call events."""
    body = (
        b'{"message": {"content": "", "tool_calls": ['
        b'{"function": {"name": "bash_exec", "arguments": {"command": "ls"}}}'
        b']}, "done": true}\n'
    )
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/chat", body=body)

    events = list(clod.stream_ollama([{"role": "user", "content": "run ls"}], "m", mock_cfg))
    tc_events = [e for e in events if e["type"] == "tool_call"]
    assert len(tc_events) == 1
    assert tc_events[0]["name"] == "bash_exec"
    assert tc_events[0]["arguments"] == {"command": "ls"}


@resp_lib.activate
def test_stream_ollama_skips_empty_lines(mock_cfg):
    """Empty lines in the NDJSON body are silently skipped."""
    body = (
        b"\n"
        b'{"message": {"content": "hi"}, "done": false}\n'
        b"\n"
        b'{"message": {"content": ""}, "done": true}\n'
    )
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/chat", body=body)

    events = list(clod.stream_ollama([{"role": "user", "content": "x"}], "m", mock_cfg))
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert tokens == ["hi"]


# ── stream_openai_compat ──────────────────────────────────────────────────────


@resp_lib.activate
def test_stream_openai_compat_tokens(mock_cfg):
    """SSE stream with two delta chunks yields two token events."""
    body = (
        b'data: {"choices": [{"delta": {"content": "hi"}}]}\n'
        b'data: {"choices": [{"delta": {"content": " there"}}]}\n'
        b"data: [DONE]\n"
    )
    resp_lib.add(resp_lib.POST, "http://localhost:4000/v1/chat/completions", body=body)

    events = list(
        clod.stream_openai_compat(
            [{"role": "user", "content": "hello"}],
            "claude-sonnet",
            "http://localhost:4000",
            "sk-local-dev",
        )
    )
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert tokens == ["hi", " there"]


@resp_lib.activate
def test_stream_openai_compat_done_marker(mock_cfg):
    """[DONE] marker stops iteration; final done event accumulates content."""
    body = (
        b'data: {"choices": [{"delta": {"content": "answer"}}]}\n'
        b"data: [DONE]\n"
        b'data: {"choices": [{"delta": {"content": "ignored"}}]}\n'
    )
    resp_lib.add(resp_lib.POST, "http://localhost:4000/v1/chat/completions", body=body)

    events = list(
        clod.stream_openai_compat(
            [{"role": "user", "content": "q"}],
            "claude-sonnet",
            "http://localhost:4000",
            "sk-local-dev",
        )
    )
    done_events = [e for e in events if e["type"] == "done"]
    assert done_events[0]["message"]["content"] == "answer"
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert "ignored" not in tokens


@resp_lib.activate
def test_stream_openai_compat_connection_error(mock_cfg):
    """ConnectionError yields a single error event."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:4000/v1/chat/completions",
        body=requests.exceptions.ConnectionError(),
    )

    events = list(
        clod.stream_openai_compat(
            [{"role": "user", "content": "hi"}],
            "claude-sonnet",
            "http://localhost:4000",
            "sk-local-dev",
        )
    )
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "Cannot connect" in events[0]["text"]


@resp_lib.activate
def test_stream_openai_compat_http_error(mock_cfg):
    """HTTP 401 yields a single error event."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:4000/v1/chat/completions",
        status=401,
        body=b"Unauthorized",
    )

    events = list(
        clod.stream_openai_compat(
            [{"role": "user", "content": "hi"}],
            "claude-sonnet",
            "http://localhost:4000",
            "sk-local-dev",
        )
    )
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "401" in events[0]["text"]


# ── stream_and_render ─────────────────────────────────────────────────────────


def _make_gen(*events):
    """Helper: create a generator from a sequence of event dicts."""
    return (e for e in events)


def test_stream_and_render_tokens_accumulated(fake_console):
    """Token events are joined into the returned content string."""
    gen = _make_gen(
        {"type": "token", "text": "hello "},
        {"type": "token", "text": "world"},
        {"type": "done", "message": {"role": "assistant", "content": "hello world"}},
    )
    content, tool_calls = clod.stream_and_render(gen)
    assert content == "hello world"
    assert tool_calls == []


def test_stream_and_render_error_returns_empty(fake_console):
    """An error event causes stream_and_render to return ('', [])."""
    gen = _make_gen({"type": "error", "text": "connection refused"})
    content, tool_calls = clod.stream_and_render(gen)
    assert content == ""
    assert tool_calls == []


def test_stream_and_render_tool_calls_returned(fake_console):
    """Tool call events are collected and returned in the second element."""
    tc = {"type": "tool_call", "name": "bash_exec", "arguments": {"command": "echo hi"}}
    gen = _make_gen(tc)
    content, tool_calls = clod.stream_and_render(gen)
    assert tool_calls == [tc]


def test_stream_and_render_empty_gen(fake_console):
    """Empty generator returns ('', [])."""
    gen = _make_gen()
    content, tool_calls = clod.stream_and_render(gen)
    assert content == ""
    assert tool_calls == []


def test_stream_and_render_multiple_tool_calls(fake_console):
    """Multiple tool call events are all collected."""
    tc1 = {"type": "tool_call", "name": "read_file", "arguments": {"path": "/tmp/a"}}
    tc2 = {"type": "tool_call", "name": "bash_exec", "arguments": {"command": "pwd"}}
    gen = _make_gen(tc1, tc2)
    _, tool_calls = clod.stream_and_render(gen)
    assert len(tool_calls) == 2
