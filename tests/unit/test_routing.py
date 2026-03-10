"""
Unit tests for smart model routing: INTENT_MODEL_MAP and _route_to_model().
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod


class CaptureConsole:
    """Console that captures print output for assertion."""

    def __init__(self):
        self.output = []

    def print(self, *args, **kwargs):
        self.output.append(" ".join(str(a) for a in args))

    def input(self, *args, **kwargs):
        return ""

    def status(self, *args, **kwargs):
        import contextlib

        return contextlib.nullcontext()


# ---------- INTENT_MODEL_MAP tests ----------


def test_intent_model_map():
    """INTENT_MODEL_MAP maps intents to correct Ollama models or None."""
    m = clod.INTENT_MODEL_MAP
    assert m["chat"] == "llama3.1:8b"
    assert m["code"] == "qwen2.5-coder:14b"
    assert m["reason"] == "deepseek-r1:14b"
    assert m["vision"] == "qwen2.5vl:7b"
    assert m["image_gen"] is None
    assert m["image_edit"] is None
    assert m["video_gen"] is None


# ---------- _route_to_model tests ----------


def test_route_switches_model(mock_session_state, monkeypatch):
    """When intent differs from current model, _ensure_model_ready is called."""
    mock_session_state["model"] = "llama3.1:8b"
    calls = []

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        calls.append((target, confirm))
        session_state["model"] = target
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    console = CaptureConsole()
    result = clod._route_to_model("code", 0.95, mock_session_state, console)
    assert result is True
    assert len(calls) == 1
    assert calls[0] == ("qwen2.5-coder:14b", False)


def test_no_switch_same_model(mock_session_state, monkeypatch):
    """When current model matches intent's model, no switch occurs."""
    mock_session_state["model"] = "qwen2.5-coder:14b"
    calls = []

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        calls.append(target)
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    console = CaptureConsole()
    result = clod._route_to_model("code", 0.95, mock_session_state, console)
    assert result is True
    assert len(calls) == 0


def test_no_switch_low_confidence(mock_session_state, monkeypatch):
    """When confidence < 0.8, no switch regardless of intent."""
    mock_session_state["model"] = "llama3.1:8b"
    calls = []

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        calls.append(target)
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    console = CaptureConsole()
    result = clod._route_to_model("code", 0.65, mock_session_state, console)
    assert result is True
    assert len(calls) == 0


def test_no_route_disabled(mock_session_state):
    """When intent_enabled is False, returns True without switching."""
    mock_session_state["intent_enabled"] = False
    mock_session_state["model"] = "llama3.1:8b"
    console = CaptureConsole()
    result = clod._route_to_model("code", 0.95, mock_session_state, console)
    assert result is True
    assert mock_session_state["model"] == "llama3.1:8b"


def test_confirmation_message(mock_session_state, monkeypatch):
    """When a switch occurs, console output contains 'Switching to' and target model."""
    mock_session_state["model"] = "llama3.1:8b"

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        session_state["model"] = target
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    console = CaptureConsole()
    clod._route_to_model("code", 0.95, mock_session_state, console)
    combined = " ".join(console.output)
    assert "Switching to" in combined
    assert "qwen2.5-coder:14b" in combined


def test_no_confirmation_same_model(mock_session_state, monkeypatch):
    """When no switch needed, no 'Switching' message is printed."""
    mock_session_state["model"] = "qwen2.5-coder:14b"

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    console = CaptureConsole()
    clod._route_to_model("code", 0.95, mock_session_state, console)
    combined = " ".join(console.output)
    assert "Switching" not in combined


def test_skip_non_model_intents(mock_session_state, monkeypatch):
    """For image_gen/image_edit/video_gen, returns True without calling _ensure_model_ready."""
    calls = []

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        calls.append(target)
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    console = CaptureConsole()
    for intent in ("image_gen", "image_edit", "video_gen"):
        result = clod._route_to_model(intent, 0.95, mock_session_state, console)
        assert result is True
    assert len(calls) == 0


def test_no_route_cloud_model(mock_session_state, monkeypatch):
    """When current model is a cloud model, no routing occurs."""
    mock_session_state["model"] = "claude-sonnet"
    calls = []

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        calls.append(target)
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    console = CaptureConsole()
    result = clod._route_to_model("code", 0.95, mock_session_state, console)
    assert result is True
    assert len(calls) == 0


def test_route_failure_graceful(mock_session_state, monkeypatch):
    """When _ensure_model_ready returns False, _route_to_model returns False."""
    mock_session_state["model"] = "llama3.1:8b"

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        return False

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    console = CaptureConsole()
    result = clod._route_to_model("code", 0.95, mock_session_state, console)
    assert result is False
    assert mock_session_state["model"] == "llama3.1:8b"
