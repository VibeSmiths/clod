"""
Integration tests: run the full infer() function against mock HTTP servers.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import infer, TokenBudget


# Suppress Rich console output during integration tests
@pytest.fixture(autouse=True)
def _quiet_console(monkeypatch):
    class _FakeConsole:
        def print(self, *a, **k):
            pass

        def input(self, *a, **k):
            return ""

        def status(self, *a, **k):
            import contextlib
            return contextlib.nullcontext()

    monkeypatch.setattr(clod, "console", _FakeConsole())


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_infer_ollama_basic(integration_cfg):
    """
    infer() with a local model against the mock Ollama server
    returns a non-empty string.
    """
    messages = [{"role": "user", "content": "Hello"}]
    result = infer(
        messages,
        model="qwen2.5-coder:14b",
        pipeline=None,
        cfg=integration_cfg,
        tools_on=False,
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_infer_offline_ignores_cloud_model(integration_cfg):
    """
    With offline=True and a cloud model, infer() should redirect to the
    local default and call the Ollama mock (returning a non-empty string).
    """
    messages = [{"role": "user", "content": "Hello"}]
    result = infer(
        messages,
        model="claude-sonnet",
        pipeline=None,
        cfg=integration_cfg,
        tools_on=False,
        offline=True,
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_infer_offline_strips_pipeline(integration_cfg):
    """
    With offline=True and a pipeline set, infer() strips the pipeline
    and falls back to the Ollama mock.
    """
    messages = [{"role": "user", "content": "Hello"}]
    result = infer(
        messages,
        model="qwen2.5-coder:14b",
        pipeline="code_review",
        cfg=integration_cfg,
        tools_on=False,
        offline=True,
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_infer_litellm_basic(integration_cfg):
    """
    With a cloud model prefix (no offline), infer() routes to the
    LiteLLM mock and returns a non-empty string.
    """
    messages = [{"role": "user", "content": "Hello"}]
    result = infer(
        messages,
        model="claude-sonnet",
        pipeline=None,
        cfg=integration_cfg,
        tools_on=False,
        offline=False,
    )
    assert isinstance(result, str)
    assert len(result) > 0
