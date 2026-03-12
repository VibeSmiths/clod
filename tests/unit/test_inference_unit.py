"""
Unit tests for infer() — ported from tests/integration/test_inference.py.

Uses the `responses` library to mock HTTP endpoints instead of http.server threads.
"""

import sys
import pathlib
import json

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import responses
from clod import infer

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _quiet_console(monkeypatch, fake_console):
    """Use the shared fake_console fixture to suppress Rich output."""
    pass  # fake_console already monkeypatches clod.console


@pytest.fixture
def inference_cfg(mock_cfg):
    """Config dict suitable for inference tests (extends mock_cfg)."""
    return mock_cfg


# ── Helpers ───────────────────────────────────────────────────────────────────

_OLLAMA_CHAT_BODY = json.dumps(
    {
        "message": {"role": "assistant", "content": "unit test response"},
        "done": True,
    }
)

_OLLAMA_TAGS_BODY = json.dumps({"models": [{"name": "qwen2.5-coder:14b"}]})

_LITELLM_SSE_BODY = (
    'data: {"choices": [{"delta": {"content": "test"}, "finish_reason": null}]}\n\n'
    "data: [DONE]\n\n"
)


def _register_ollama_mocks(ollama_url: str = "http://localhost:11434"):
    """Register responses mocks for Ollama /api/tags and /api/chat."""
    responses.add(
        responses.GET,
        f"{ollama_url}/api/tags",
        json={"models": [{"name": "qwen2.5-coder:14b"}]},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{ollama_url}/api/chat",
        body=_OLLAMA_CHAT_BODY,
        status=200,
        content_type="application/x-ndjson",
    )


def _register_litellm_mocks(litellm_url: str = "http://localhost:4000"):
    """Register responses mock for LiteLLM /v1/chat/completions."""
    responses.add(
        responses.POST,
        f"{litellm_url}/v1/chat/completions",
        body=_LITELLM_SSE_BODY,
        status=200,
        content_type="text/event-stream",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@responses.activate
def test_infer_ollama_basic(inference_cfg):
    """
    infer() with a local model against mocked Ollama returns a non-empty string.
    """
    _register_ollama_mocks()
    messages = [{"role": "user", "content": "Hello"}]
    result = infer(
        messages,
        model="qwen2.5-coder:14b",
        pipeline=None,
        cfg=inference_cfg,
        tools_on=False,
    )
    assert isinstance(result, str)
    assert len(result) > 0


@responses.activate
def test_infer_offline_ignores_cloud_model(inference_cfg):
    """
    With offline=True and a cloud model, infer() redirects to the local default
    and calls the Ollama mock (returning a non-empty string).
    """
    _register_ollama_mocks()
    messages = [{"role": "user", "content": "Hello"}]
    result = infer(
        messages,
        model="claude-sonnet",
        pipeline=None,
        cfg=inference_cfg,
        tools_on=False,
        offline=True,
    )
    assert isinstance(result, str)
    assert len(result) > 0


@responses.activate
def test_infer_offline_strips_pipeline(inference_cfg):
    """
    With offline=True and a pipeline set, infer() strips the pipeline
    and falls back to the Ollama mock.
    """
    _register_ollama_mocks()
    messages = [{"role": "user", "content": "Hello"}]
    result = infer(
        messages,
        model="qwen2.5-coder:14b",
        pipeline="code_review",
        cfg=inference_cfg,
        tools_on=False,
        offline=True,
    )
    assert isinstance(result, str)
    assert len(result) > 0


@responses.activate
def test_infer_litellm_basic(inference_cfg):
    """
    With a cloud model prefix (no offline), infer() routes to the LiteLLM
    mock and returns a non-empty string.
    """
    _register_litellm_mocks()
    messages = [{"role": "user", "content": "Hello"}]
    result = infer(
        messages,
        model="claude-sonnet",
        pipeline=None,
        cfg=inference_cfg,
        tools_on=False,
        offline=False,
    )
    assert isinstance(result, str)
    assert len(result) > 0
