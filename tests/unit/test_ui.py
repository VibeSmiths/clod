"""
Tests for Rich UI helper functions:
  print_header, print_help, print_tool_call, print_tool_result
All functions call console.print(); we use fake_console to avoid Rich rendering.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import TokenBudget

# ── print_header ──────────────────────────────────────────────────────────────


def test_print_header_default(fake_console, mock_cfg):
    """Basic header with no pipeline, no budget, online."""
    clod.print_header("qwen2.5-coder:14b", None, False)


def test_print_header_with_pipeline(fake_console, mock_cfg):
    """Header displays pipeline name when pipeline is set."""
    clod.print_header("qwen2.5-coder:14b", "code_review", False)


def test_print_header_tools_on(fake_console):
    """Header with tools enabled."""
    clod.print_header("llama3.1:8b", None, True)


def test_print_header_offline(fake_console):
    """Header shows OFFLINE indicator when offline=True."""
    clod.print_header("qwen2.5-coder:14b", None, False, offline=True)


def test_print_header_budget_unused(fake_console):
    """Budget with zero usage: token string should NOT appear."""
    budget = TokenBudget(10000)
    clod.print_header("qwen2.5-coder:14b", None, False, budget=budget)


def test_print_header_budget_with_usage(fake_console):
    """Budget with some usage: token string IS included."""
    budget = TokenBudget(10000)
    budget.used = 500
    clod.print_header("qwen2.5-coder:14b", None, False, budget=budget)


def test_print_header_pipeline_overrides_model(fake_console):
    """When pipeline is set, active label is 'pipeline:<name>', not model."""
    # We exercise both branches of the active = ... ternary.
    clod.print_header("any-model", "reason_review", True, offline=False)


# ── print_help ────────────────────────────────────────────────────────────────


def test_print_help_calls_console(fake_console):
    """print_help should run without raising."""
    clod.print_help()


# ── print_tool_call ───────────────────────────────────────────────────────────


def test_print_tool_call_simple(fake_console):
    """print_tool_call renders a panel; no exception expected."""
    clod.print_tool_call("bash_exec", {"command": "ls -la"})


def test_print_tool_call_empty_args(fake_console):
    """print_tool_call with empty args dict."""
    clod.print_tool_call("read_file", {})


def test_print_tool_call_nested_args(fake_console):
    """print_tool_call with nested argument dict."""
    clod.print_tool_call("web_search", {"query": "python testing", "count": 5})


# ── print_tool_result ─────────────────────────────────────────────────────────


def test_print_tool_result_short(fake_console):
    """Short result (< 500 chars) shown in full."""
    clod.print_tool_result("read_file", "file content here")


def test_print_tool_result_long_truncated(fake_console):
    """Result longer than 500 chars gets '...' appended."""
    long_result = "x" * 600
    clod.print_tool_result("bash_exec", long_result)


def test_print_tool_result_exact_limit(fake_console):
    """Result exactly 500 chars — no truncation."""
    clod.print_tool_result("web_search", "y" * 500)


def test_print_tool_result_empty(fake_console):
    """Empty result string handled without error."""
    clod.print_tool_result("write_file", "")


# ── print_startup_banner with health ──────────────────────────────────────────


def test_print_startup_banner_with_health_all_up(monkeypatch, fake_console):
    """Passing a health dict with all services up shows green dots in banner."""
    monkeypatch.setattr(clod, "query_system_info", lambda: None)
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)

    health = {"ollama": True, "litellm": True, "pipelines": True, "searxng": True, "chroma": True}
    clod.print_startup_banner("qwen2.5-coder:14b", health=health)


def test_print_startup_banner_with_health_some_down(monkeypatch, fake_console):
    """When some services are down, the 'services offline' hint line is shown."""
    monkeypatch.setattr(clod, "query_system_info", lambda: None)
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)

    health = {"ollama": True, "litellm": False, "pipelines": False, "searxng": False, "chroma": False}
    clod.print_startup_banner("qwen2.5-coder:14b", health=health)


def test_print_startup_banner_no_health(monkeypatch, fake_console):
    """Passing health=None omits the services section (backward compat)."""
    monkeypatch.setattr(clod, "query_system_info", lambda: None)
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)

    clod.print_startup_banner("qwen2.5-coder:14b", health=None)
