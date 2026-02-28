"""
Basic smoke tests for clod.py
"""

import json
import sys
import os
import pathlib
import tempfile

import pytest

# Make clod importable from project root
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import clod

# ── Config ─────────────────────────────────────────────────────────────────────


def test_load_config_returns_defaults(tmp_path, monkeypatch):
    """load_config() returns all expected keys when no config file exists."""
    monkeypatch.setattr(clod, "config_path", lambda: tmp_path / "nonexistent.json")
    cfg = clod.load_config()
    assert "ollama_url" in cfg
    assert "litellm_url" in cfg
    assert "default_model" in cfg
    assert "enable_tools" in cfg
    assert cfg["default_model"] == "qwen2.5-coder:14b"


def test_load_config_merges_user_file(tmp_path, monkeypatch):
    """load_config() merges user settings over defaults."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"default_model": "llama3.1:8b", "enable_tools": True}))
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)
    cfg = clod.load_config()
    assert cfg["default_model"] == "llama3.1:8b"
    assert cfg["enable_tools"] is True
    assert cfg["ollama_url"] == "http://localhost:11434"  # default preserved


def test_save_and_reload_config(tmp_path, monkeypatch):
    """save_config() persists values that load_config() can read back."""
    cfg_file = tmp_path / "clod" / "config.json"
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)
    data = clod.load_config()
    data["default_model"] = "deepseek-r1:14b"
    clod.save_config(data)
    reloaded = clod.load_config()
    assert reloaded["default_model"] == "deepseek-r1:14b"


# ── Adapter selection ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "model,pipeline,expected",
    [
        ("qwen2.5-coder:14b", None, "ollama"),
        ("deepseek-r1:14b", None, "ollama"),
        ("claude-sonnet", None, "litellm"),
        ("gpt-4o", None, "litellm"),
        ("gemini-flash", None, "litellm"),
        ("groq-fast", None, "litellm"),
        ("qwen2.5-coder:14b", "code_review", "pipeline"),
        ("claude-sonnet", "reason_review", "pipeline"),
    ],
)
def test_pick_adapter(model, pipeline, expected):
    cfg = clod.load_config()
    assert clod.pick_adapter(model, pipeline, cfg) == expected


# ── Tool executors ─────────────────────────────────────────────────────────────


def test_tool_read_file_existing(tmp_path):
    f = tmp_path / "hello.txt"
    f.write_text("hello world\n")
    result = clod.tool_read_file({"path": str(f)})
    assert "hello world" in result


def test_tool_read_file_missing():
    result = clod.tool_read_file({"path": "/nonexistent/path/file.txt"})
    assert "not found" in result.lower() or "error" in result.lower()


def test_tool_read_file_line_limit(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("\n".join(str(i) for i in range(100)))
    result = clod.tool_read_file({"path": str(f), "lines": 5})
    lines = result.strip().splitlines()
    assert len(lines) <= 5


def test_tool_write_file_creates_file(tmp_path):
    out = tmp_path / "out.txt"
    result = clod.tool_write_file({"path": str(out), "content": "test content"})
    assert out.exists()
    assert out.read_text() == "test content"
    assert "Wrote" in result


def test_tool_write_file_append(tmp_path):
    out = tmp_path / "append.txt"
    out.write_text("line1\n")
    clod.tool_write_file({"path": str(out), "content": "line2\n", "append": True})
    assert out.read_text() == "line1\nline2\n"


# ── Tool definitions format ────────────────────────────────────────────────────


def test_tool_definitions_valid_structure():
    """All tools follow the OpenAI function-calling schema."""
    for tool in clod.TOOL_DEFINITIONS:
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
    """Every tool in TOOL_DEFINITIONS has a corresponding executor branch."""
    tool_names = {t["function"]["name"] for t in clod.TOOL_DEFINITIONS}
    # These are the tools handled in execute_tool()
    handled = {"bash_exec", "read_file", "write_file", "web_search"}
    assert tool_names == handled


# ── Slash command handler ──────────────────────────────────────────────────────


def test_slash_clear_empties_messages():
    state = {"model": "qwen2.5-coder:14b", "pipeline": None, "tools_on": False, "system": None}
    messages = [{"role": "user", "content": "hi"}]
    # patch console.print to avoid actual output
    clod.console = type("FakeConsole", (), {"print": lambda *a, **k: None})()
    handled = clod.handle_slash("/clear", state, messages)
    assert handled is True
    assert messages == []


def test_slash_model_updates_state():
    state = {
        "model": "qwen2.5-coder:14b",
        "pipeline": "code_review",
        "tools_on": False,
        "system": None,
    }
    messages = []
    clod.console = type("FakeConsole", (), {"print": lambda *a, **k: None})()
    handled = clod.handle_slash("/model deepseek-r1:14b", state, messages)
    assert handled is True
    assert state["model"] == "deepseek-r1:14b"
    assert state["pipeline"] is None  # pipeline cleared on model switch


def test_slash_pipeline_sets_and_clears():
    state = {"model": "qwen2.5-coder:14b", "pipeline": None, "tools_on": False, "system": None}
    messages = []
    clod.console = type("FakeConsole", (), {"print": lambda *a, **k: None})()
    clod.handle_slash("/pipeline reason_review", state, messages)
    assert state["pipeline"] == "reason_review"
    clod.handle_slash("/pipeline off", state, messages)
    assert state["pipeline"] is None


def test_slash_unknown_returns_false():
    state = {"model": "x", "pipeline": None, "tools_on": False, "system": None}
    clod.console = type("FakeConsole", (), {"print": lambda *a, **k: None})()
    assert clod.handle_slash("/nonexistent", state, []) is False


def test_slash_system_inserts_message():
    state = {"model": "x", "pipeline": None, "tools_on": False, "system": None}
    messages = []
    clod.console = type("FakeConsole", (), {"print": lambda *a, **k: None})()
    clod.handle_slash("/system you are a pirate", state, messages)
    assert messages[0]["role"] == "system"
    assert "pirate" in messages[0]["content"]
