"""
Unit tests for handle_slash() — uses a complete session_state.
"""

import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import handle_slash, TokenBudget


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_state(mock_cfg):
    """Return a fresh, complete session_state dict."""
    return {
        "model": "qwen2.5-coder:14b",
        "pipeline": None,
        "tools_on": False,
        "system": None,
        "cfg": mock_cfg,
        "budget": TokenBudget(10000),
        "offline": False,
    }


# ── /clear ─────────────────────────────────────────────────────────────────────


def test_slash_clear_empties_messages(fake_console, mock_cfg):
    state = _make_state(mock_cfg)
    messages = [{"role": "user", "content": "hi"}]
    handled = handle_slash("/clear", state, messages)
    assert handled is True
    assert messages == []


# ── /model ─────────────────────────────────────────────────────────────────────


def test_slash_model_updates_state(monkeypatch, mock_cfg):
    """
    /model X updates session_state["model"], clears pipeline,
    and calls warmup_ollama_model for non-cloud models.
    """
    warmup_called = []

    monkeypatch.setattr(
        clod,
        "warmup_ollama_model",
        lambda model, cfg: warmup_called.append(model),
    )
    monkeypatch.setattr(clod, "console", type("C", (), {"print": lambda *a, **k: None})())

    state = _make_state(mock_cfg)
    state["pipeline"] = "code_review"
    messages = []

    handled = handle_slash("/model deepseek-r1:14b", state, messages)

    assert handled is True
    assert state["model"] == "deepseek-r1:14b"
    assert state["pipeline"] is None  # pipeline cleared on model switch
    assert "deepseek-r1:14b" in warmup_called


def test_slash_model_no_warmup_for_cloud(monkeypatch, mock_cfg):
    """
    /model claude-sonnet does NOT call warmup_ollama_model.
    """
    warmup_called = []

    monkeypatch.setattr(
        clod,
        "warmup_ollama_model",
        lambda model, cfg: warmup_called.append(model),
    )
    monkeypatch.setattr(clod, "console", type("C", (), {"print": lambda *a, **k: None})())

    state = _make_state(mock_cfg)
    handle_slash("/model claude-sonnet", state, [])

    assert state["model"] == "claude-sonnet"
    assert warmup_called == []  # no warmup for cloud models


# ── /pipeline ──────────────────────────────────────────────────────────────────


def test_slash_pipeline_sets(fake_console, mock_cfg):
    """/pipeline code_review sets pipeline in session_state."""
    state = _make_state(mock_cfg)
    handled = handle_slash("/pipeline code_review", state, [])
    assert handled is True
    assert state["pipeline"] == "code_review"


def test_slash_pipeline_clears(fake_console, mock_cfg):
    """/pipeline off sets pipeline to None."""
    state = _make_state(mock_cfg)
    state["pipeline"] = "code_review"
    handle_slash("/pipeline off", state, [])
    assert state["pipeline"] is None


# ── /tools ─────────────────────────────────────────────────────────────────────


def test_slash_tools_on_off(fake_console, mock_cfg):
    """/tools on/off toggles tools_on in session_state."""
    state = _make_state(mock_cfg)
    assert state["tools_on"] is False

    handle_slash("/tools on", state, [])
    assert state["tools_on"] is True

    handle_slash("/tools off", state, [])
    assert state["tools_on"] is False


# ── /offline ───────────────────────────────────────────────────────────────────


def test_slash_offline_enables(fake_console, mock_cfg):
    """/offline sets offline=True."""
    state = _make_state(mock_cfg)
    handle_slash("/offline", state, [])
    assert state["offline"] is True


def test_slash_offline_disables(fake_console, mock_cfg):
    """/offline off sets offline=False."""
    state = _make_state(mock_cfg)
    state["offline"] = True
    handle_slash("/offline off", state, [])
    assert state["offline"] is False


# ── /tokens ────────────────────────────────────────────────────────────────────


def test_slash_tokens_no_usage(fake_console, mock_cfg):
    """/tokens with 0 used prints 'No Claude tokens'."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(a)

    state = _make_state(mock_cfg)
    handle_slash("/tokens", state, [])

    assert any("No Claude tokens" in str(msg) for msg in printed)


def test_slash_tokens_with_usage(monkeypatch, mock_cfg):
    """/tokens with some tokens used prints status_str."""
    printed = []
    monkeypatch.setattr(
        clod,
        "console",
        type("C", (), {"print": lambda self, *a, **k: printed.append(a)})(),
    )

    state = _make_state(mock_cfg)
    state["budget"].used = 1234

    handle_slash("/tokens", state, [])

    all_output = " ".join(str(m) for m in printed)
    assert "1,234" in all_output or "1234" in all_output


# ── /system ────────────────────────────────────────────────────────────────────


def test_slash_system_inserts_message(fake_console, mock_cfg):
    """/system X inserts a system message into the conversation."""
    state = _make_state(mock_cfg)
    messages = []
    handle_slash("/system you are a pirate", state, messages)
    assert len(messages) == 1
    assert messages[0]["role"] == "system"
    assert "pirate" in messages[0]["content"]


# ── unknown command ─────────────────────────────────────────────────────────────


def test_slash_unknown_returns_false(fake_console, mock_cfg):
    """An unrecognised slash command returns False."""
    state = _make_state(mock_cfg)
    result = handle_slash("/nonexistent", state, [])
    assert result is False


# ── /save ──────────────────────────────────────────────────────────────────────


def test_slash_save_writes_json(fake_console, tmp_path, mock_cfg):
    """/save writes the conversation as a JSON file."""
    state = _make_state(mock_cfg)
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]
    save_file = tmp_path / "convo.json"

    handle_slash(f"/save {save_file}", state, messages)

    assert save_file.exists()
    loaded = json.loads(save_file.read_text())
    assert loaded == messages
