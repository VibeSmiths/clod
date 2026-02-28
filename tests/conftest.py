"""
Shared pytest fixtures for clod test suite.
"""

import sys
import pathlib

# Make clod importable from the project root
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
import clod


@pytest.fixture
def fake_console(monkeypatch):
    """Monkeypatch clod.console with a no-op object."""

    class _FakeConsole:
        def print(self, *args, **kwargs):
            pass

        def input(self, *args, **kwargs):
            return ""

        def status(self, *args, **kwargs):
            import contextlib

            return contextlib.nullcontext()

    fc = _FakeConsole()
    monkeypatch.setattr(clod, "console", fc)
    return fc


@pytest.fixture
def mock_cfg():
    """Return a minimal config dict with localhost URLs."""
    return {
        "ollama_url": "http://localhost:11434",
        "litellm_url": "http://localhost:4000",
        "litellm_key": "sk-local-dev",
        "pipelines_url": "http://localhost:9099",
        "searxng_url": "http://localhost:8080",
        "default_model": "qwen2.5-coder:14b",
        "pipeline": None,
        "enable_tools": False,
        "token_budget": 10000,
    }


@pytest.fixture
def mock_session_state(mock_cfg):
    """Return a complete session_state dict suitable for handle_slash tests."""
    return {
        "model": "qwen2.5-coder:14b",
        "pipeline": None,
        "tools_on": False,
        "system": None,
        "cfg": mock_cfg,
        "budget": clod.TokenBudget(10000),
        "offline": False,
    }
