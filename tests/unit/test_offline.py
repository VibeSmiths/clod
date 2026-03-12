"""
Unit tests for offline gating: _is_cloud_request, _enforce_offline,
/search slash command, and print_header offline/search indicators.
"""

import io

import pytest
from rich.console import Console

import clod

# ── _is_cloud_request ─────────────────────────────────────────────────────────


def test_is_cloud_request_claude():
    assert clod._is_cloud_request("claude-3-opus") is True


def test_is_cloud_request_gpt():
    assert clod._is_cloud_request("gpt-4") is True


def test_is_cloud_request_local():
    assert clod._is_cloud_request("qwen2.5-coder:14b") is False


def test_is_cloud_request_local_llama():
    assert clod._is_cloud_request("llama3.1:8b") is False


# ── _enforce_offline ──────────────────────────────────────────────────────────


def test_enforce_offline_blocks_cloud():
    session = {"offline": True}
    result = clod._enforce_offline("claude-3-opus", session)
    assert result is not None
    assert "claude-3-opus" in result
    assert "blocked" in result.lower() or "offline" in result.lower()


def test_enforce_offline_allows_local():
    session = {"offline": True}
    result = clod._enforce_offline("qwen2.5-coder:14b", session)
    assert result is None


def test_enforce_offline_allows_when_online():
    session = {"offline": False}
    result = clod._enforce_offline("claude-3-opus", session)
    assert result is None


# ── print_header indicators ──────────────────────────────────────────────────


def test_offline_indicator_in_header(monkeypatch):
    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=True, width=120)
    monkeypatch.setattr(clod, "console", test_console)
    clod.print_header("qwen2.5-coder:14b", None, False, offline=True)
    output = buf.getvalue()
    assert "OFFLINE" in output


def test_online_indicator_in_header(monkeypatch):
    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=True, width=120)
    monkeypatch.setattr(clod, "console", test_console)
    clod.print_header("qwen2.5-coder:14b", None, False, offline=False)
    output = buf.getvalue()
    assert "online" in output


# ── /search slash command ────────────────────────────────────────────────────


def test_search_toggle_on(monkeypatch, mock_session_state):
    monkeypatch.setattr(clod, "console", Console(file=io.StringIO(), force_terminal=True))
    mock_session_state["features"] = {"web_search_enabled": False}
    clod.handle_slash("/search on", mock_session_state, [])
    assert mock_session_state["features"]["web_search_enabled"] is True


def test_search_toggle_off(monkeypatch, mock_session_state):
    monkeypatch.setattr(clod, "console", Console(file=io.StringIO(), force_terminal=True))
    mock_session_state["features"] = {"web_search_enabled": True}
    clod.handle_slash("/search off", mock_session_state, [])
    assert mock_session_state["features"]["web_search_enabled"] is False


def test_search_toggle_no_arg(monkeypatch, mock_session_state):
    monkeypatch.setattr(clod, "console", Console(file=io.StringIO(), force_terminal=True))
    mock_session_state["features"] = {"web_search_enabled": True}
    clod.handle_slash("/search", mock_session_state, [])
    assert mock_session_state["features"]["web_search_enabled"] is False
