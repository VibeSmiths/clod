"""
Tests for the infer() inference loop.
All HTTP/streaming is mocked via monkeypatch to avoid real network calls.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import TokenBudget

# ── Helpers ───────────────────────────────────────────────────────────────────


def _patch_stream_and_render(monkeypatch, return_values):
    """
    Patch stream_and_render to return values from a list in sequence.
    Each item is a (content, tool_calls) tuple.
    """
    call_iter = iter(return_values)

    def fake_stream_and_render(gen):
        return next(call_iter)

    monkeypatch.setattr(clod, "stream_and_render", fake_stream_and_render)


def _patch_ensure(monkeypatch, result=True):
    monkeypatch.setattr(clod, "ensure_ollama_model", lambda m, c: result)


# ── Ollama adapter ────────────────────────────────────────────────────────────


def test_infer_ollama_basic(monkeypatch, fake_console, mock_cfg):
    """Local model uses ollama adapter and returns final content."""
    _patch_ensure(monkeypatch)
    _patch_stream_and_render(monkeypatch, [("response text", [])])

    result = clod.infer(
        [{"role": "user", "content": "hi"}],
        "qwen2.5-coder:14b",
        None,
        mock_cfg,
        False,
    )
    assert result == "response text"


def test_infer_ollama_model_unavailable(monkeypatch, fake_console, mock_cfg):
    """When ensure_ollama_model returns False, infer returns an error string."""
    _patch_ensure(monkeypatch, result=False)

    result = clod.infer(
        [{"role": "user", "content": "hi"}],
        "nonexistent-model:7b",
        None,
        mock_cfg,
        False,
    )
    assert "Could not obtain model" in result


# ── LiteLLM adapter ───────────────────────────────────────────────────────────


def test_infer_litellm_adapter(monkeypatch, fake_console, mock_cfg):
    """Model starting with 'claude-' uses litellm adapter."""
    _patch_stream_and_render(monkeypatch, [("claude says hi", [])])

    # No ensure_ollama_model call expected for litellm
    result = clod.infer(
        [{"role": "user", "content": "hello"}],
        "claude-sonnet-4-6",
        None,
        mock_cfg,
        False,
    )
    assert result == "claude says hi"


def test_infer_litellm_gpt_prefix(monkeypatch, fake_console, mock_cfg):
    """Model starting with 'gpt-' also uses litellm adapter."""
    _patch_stream_and_render(monkeypatch, [("gpt reply", [])])

    result = clod.infer(
        [{"role": "user", "content": "q"}],
        "gpt-4o",
        None,
        mock_cfg,
        False,
    )
    assert result == "gpt reply"


# ── Pipeline adapter ──────────────────────────────────────────────────────────


def test_infer_pipeline_adapter(monkeypatch, fake_console, mock_cfg):
    """When pipeline is set, the pipeline adapter is used."""
    _patch_stream_and_render(monkeypatch, [("pipeline result", [])])

    result = clod.infer(
        [{"role": "user", "content": "review this"}],
        "qwen2.5-coder:14b",
        "code_review",
        mock_cfg,
        False,
    )
    assert result == "pipeline result"


# ── Offline mode ──────────────────────────────────────────────────────────────


def test_infer_offline_redirects_cloud_model(monkeypatch, fake_console, mock_cfg):
    """In offline mode, a cloud model is redirected to default_model."""
    _patch_ensure(monkeypatch)
    captured = {}

    def fake_stream_ollama(messages, model, cfg, tools=None):
        captured["model"] = model
        return iter([{"type": "done", "message": {"role": "assistant", "content": "local"}}])

    monkeypatch.setattr(clod, "stream_ollama", fake_stream_ollama)
    _patch_stream_and_render(monkeypatch, [("local", [])])

    result = clod.infer(
        [{"role": "user", "content": "hi"}],
        "claude-sonnet-4-6",
        None,
        mock_cfg,
        False,
        offline=True,
    )
    # Cloud model should have been swapped to default_model
    assert captured["model"] == mock_cfg["default_model"]
    assert result == "local"


def test_infer_offline_strips_pipeline(monkeypatch, fake_console, mock_cfg):
    """In offline mode, pipeline is set to None and a local model is used."""
    _patch_ensure(monkeypatch)
    captured = {}

    def fake_stream_ollama(messages, model, cfg, tools=None):
        captured["called"] = True
        return iter([])

    monkeypatch.setattr(clod, "stream_ollama", fake_stream_ollama)
    _patch_stream_and_render(monkeypatch, [("offline local", [])])

    result = clod.infer(
        [{"role": "user", "content": "hi"}],
        "qwen2.5-coder:14b",
        "code_review",
        mock_cfg,
        False,
        offline=True,
    )
    # stream_ollama should have been called (not stream_openai_compat for pipeline)
    assert captured.get("called") is True
    assert result == "offline local"


# ── Budget tracking ───────────────────────────────────────────────────────────


def test_infer_budget_add_called_for_litellm(monkeypatch, fake_console, mock_cfg):
    """budget.add() is called when using a claude- (litellm) model."""
    _patch_stream_and_render(monkeypatch, [("the answer", [])])

    budget = TokenBudget(100_000)
    clod.infer(
        [{"role": "user", "content": "count my tokens"}],
        "claude-sonnet-4-6",
        None,
        mock_cfg,
        False,
        budget=budget,
    )
    assert budget.used > 0


def test_infer_budget_not_called_for_ollama(monkeypatch, fake_console, mock_cfg):
    """budget.add() is NOT called when using ollama (local model)."""
    _patch_ensure(monkeypatch)
    _patch_stream_and_render(monkeypatch, [("local answer", [])])

    budget = TokenBudget(100_000)
    clod.infer(
        [{"role": "user", "content": "hi"}],
        "qwen2.5-coder:14b",
        None,
        mock_cfg,
        False,
        budget=budget,
    )
    assert budget.used == 0


# ── Tool call round-trip ──────────────────────────────────────────────────────


def test_infer_tool_call_loop(monkeypatch, fake_console, mock_cfg):
    """When first round returns tool_calls, execute_tool is called and loop continues."""
    _patch_ensure(monkeypatch)

    tool_call = {"type": "tool_call", "name": "bash_exec", "arguments": {"command": "echo hi"}}
    call_count = {"n": 0}

    def fake_stream_and_render(gen):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ("", [tool_call])
        return ("final answer", [])

    monkeypatch.setattr(clod, "stream_and_render", fake_stream_and_render)

    execute_calls = []

    def fake_execute_tool(name, args, console, cfg):
        execute_calls.append(name)
        return "tool_result"

    monkeypatch.setattr(clod, "execute_tool", fake_execute_tool)

    result = clod.infer(
        [{"role": "user", "content": "run something"}],
        "qwen2.5-coder:14b",
        None,
        mock_cfg,
        True,
    )
    assert result == "final answer"
    assert execute_calls == ["bash_exec"]
    assert call_count["n"] == 2


def test_infer_tool_call_adds_messages(monkeypatch, fake_console, mock_cfg):
    """Tool results are appended as 'tool' role messages."""
    _patch_ensure(monkeypatch)

    tool_call = {"type": "tool_call", "name": "read_file", "arguments": {"path": "/tmp/f"}}
    messages = [{"role": "user", "content": "read a file"}]

    call_count = {"n": 0}

    def fake_stream_and_render(gen):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return ("", [tool_call])
        return ("done", [])

    monkeypatch.setattr(clod, "stream_and_render", fake_stream_and_render)
    monkeypatch.setattr(clod, "execute_tool", lambda name, args, console, cfg: "file content")

    clod.infer(messages, "qwen2.5-coder:14b", None, mock_cfg, True)

    roles = [m["role"] for m in messages]
    assert "tool" in roles
    tool_msgs = [m for m in messages if m["role"] == "tool"]
    assert tool_msgs[0]["content"] == "file content"
    assert tool_msgs[0]["name"] == "read_file"
