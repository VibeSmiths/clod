"""
Tests for Ollama model-management functions:
  ollama_local_models, ollama_model_available, ensure_ollama_model,
  warmup_ollama_model
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import requests
import responses as resp_lib

import clod

# ── ollama_local_models ───────────────────────────────────────────────────────


@resp_lib.activate
def test_ollama_local_models_success(mock_cfg):
    """Returns list of model names from the API response."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "qwen2.5-coder:14b"}, {"name": "llama3.1:8b"}]},
    )
    models = clod.ollama_local_models(mock_cfg["ollama_url"])
    assert "qwen2.5-coder:14b" in models
    assert "llama3.1:8b" in models


@resp_lib.activate
def test_ollama_local_models_empty(mock_cfg):
    """Empty models list is handled gracefully."""
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []})
    models = clod.ollama_local_models(mock_cfg["ollama_url"])
    assert models == []


@resp_lib.activate
def test_ollama_local_models_connection_error(mock_cfg):
    """ConnectionError returns an empty list (no exception raised)."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        body=requests.exceptions.ConnectionError(),
    )
    models = clod.ollama_local_models(mock_cfg["ollama_url"])
    assert models == []


@resp_lib.activate
def test_ollama_local_models_http_error(mock_cfg):
    """HTTP 503 returns an empty list."""
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", status=503)
    models = clod.ollama_local_models(mock_cfg["ollama_url"])
    assert models == []


# ── ollama_model_available ────────────────────────────────────────────────────


@resp_lib.activate
def test_ollama_model_available_exact_match(mock_cfg):
    """Exact model name match returns True."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "qwen2.5-coder:14b"}]},
    )
    assert clod.ollama_model_available("qwen2.5-coder:14b", mock_cfg["ollama_url"]) is True


@resp_lib.activate
def test_ollama_model_available_bare_name(mock_cfg):
    """Bare model name ('llama3.1') matches 'llama3.1:latest' in the list."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "llama3.1:latest"}]},
    )
    # The function checks: model in candidates or f"{model}:latest" in available
    assert clod.ollama_model_available("llama3.1", mock_cfg["ollama_url"]) is True


@resp_lib.activate
def test_ollama_model_available_bare_name_in_candidates(mock_cfg):
    """Bare model name derived by splitting ':' from a tagged name is in candidates."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "llama3.1:8b"}]},
    )
    # candidates = {"llama3.1:8b", "llama3.1"} — bare "llama3.1" is included
    assert clod.ollama_model_available("llama3.1", mock_cfg["ollama_url"]) is True


@resp_lib.activate
def test_ollama_model_available_not_found(mock_cfg):
    """Model not in list returns False."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "other-model:7b"}]},
    )
    assert clod.ollama_model_available("qwen2.5-coder:14b", mock_cfg["ollama_url"]) is False


@resp_lib.activate
def test_ollama_model_available_empty_list(mock_cfg):
    """Empty model list always returns False."""
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []})
    assert clod.ollama_model_available("any-model", mock_cfg["ollama_url"]) is False


# ── ensure_ollama_model ───────────────────────────────────────────────────────


@resp_lib.activate
def test_ensure_ollama_model_already_available(mock_cfg, fake_console):
    """When model is available, returns True without pulling."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "qwen2.5-coder:14b"}]},
    )
    result = clod.ensure_ollama_model("qwen2.5-coder:14b", mock_cfg)
    assert result is True


@resp_lib.activate
def test_ensure_ollama_model_not_available_pulls(mock_cfg, fake_console, monkeypatch):
    """When model is not available, ollama_pull is called."""
    # First tags call: model not present
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []})
    # Second tags call (after pull): model now present
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "new-model:7b"}]},
    )

    pull_calls = []

    def fake_pull(model, url):
        pull_calls.append(model)

    monkeypatch.setattr(clod, "ollama_pull", fake_pull)

    result = clod.ensure_ollama_model("new-model:7b", mock_cfg)
    assert pull_calls == ["new-model:7b"]
    assert result is True


# ── warmup_ollama_model ───────────────────────────────────────────────────────


@resp_lib.activate
def test_warmup_ollama_model_connection_error(mock_cfg, fake_console):
    """warmup_ollama_model swallows ConnectionError silently."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        body=requests.exceptions.ConnectionError(),
    )
    # Should not raise
    clod.warmup_ollama_model("qwen2.5-coder:14b", mock_cfg)


@resp_lib.activate
def test_warmup_ollama_model_success(mock_cfg, fake_console):
    """warmup_ollama_model completes without error on a 200 response."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        json={"message": {"content": "hi"}, "done": True},
    )
    clod.warmup_ollama_model("qwen2.5-coder:14b", mock_cfg)


@resp_lib.activate
def test_warmup_ollama_model_timeout(mock_cfg, fake_console):
    """warmup_ollama_model swallows Timeout silently."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        body=requests.exceptions.Timeout(),
    )
    clod.warmup_ollama_model("qwen2.5-coder:14b", mock_cfg)
