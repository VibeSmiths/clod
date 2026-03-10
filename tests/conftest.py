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
        """Wraps a real rich.console.Console writing to /dev/null so that
        Rich components (Progress, Live, etc.) work, while keeping output
        suppressed and easy to override in tests."""

        def __init__(self):
            import io
            from rich.console import Console as _RC

            self._real = _RC(file=io.StringIO(), force_terminal=True, width=80)

        def __getattr__(self, name):
            # Delegate anything not explicitly overridden to the real Console
            return getattr(self._real, name)

        # Dunder methods are not resolved via __getattr__, so delegate explicitly
        def __enter__(self):
            return self._real.__enter__()

        def __exit__(self, *args):
            return self._real.__exit__(*args)

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
        "intent_enabled": True,
        "last_intent": None,
        "last_confidence": 0.0,
        "intent_verbose": False,
    }
