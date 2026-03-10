"""
Unit tests for VRAM management functions:
_get_loaded_models, _unload_model, _verify_vram_free,
_vram_transition_panel, _ensure_model_ready, _prepare_for_gpu_service,
_restore_after_gpu_service.
"""

import contextlib
import pathlib
import time

import pytest
import responses as resp_lib

import clod

# ── Helpers ──────────────────────────────────────────────────────────────────


class FakeConsole:
    """Capture console output for assertions."""

    def __init__(self):
        self.output = []
        self._input_response = ""

    def print(self, *args, **kwargs):
        self.output.append(str(args[0]) if args else "")

    def input(self, *args, **kwargs):
        return self._input_response

    def status(self, *args, **kwargs):
        return contextlib.nullcontext()


def _make_cfg(ollama_url="http://localhost:11434"):
    return {
        "ollama_url": ollama_url,
        "litellm_url": "http://localhost:4000",
        "litellm_key": "sk-local-dev",
        "pipelines_url": "http://localhost:9099",
        "searxng_url": "http://localhost:8080",
        "chroma_url": "http://localhost:8000",
        "default_model": "qwen2.5-coder:14b",
        "compose_file": "docker-compose.yml",
        "dotenv_file": ".env",
    }


# ── _get_loaded_models ───────────────────────────────────────────────────────


@resp_lib.activate
def test_get_loaded_models_returns_list():
    cfg = _make_cfg()
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        json={"models": [{"name": "qwen2.5-coder:14b", "size": 8000000000}]},
        status=200,
    )
    result = clod._get_loaded_models(cfg)
    assert len(result) == 1
    assert result[0]["name"] == "qwen2.5-coder:14b"


@resp_lib.activate
def test_get_loaded_models_connection_error():
    cfg = _make_cfg()
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        body=ConnectionError("refused"),
    )
    result = clod._get_loaded_models(cfg)
    assert result == []


# ── _unload_model ────────────────────────────────────────────────────────────


@resp_lib.activate
def test_unload_model_success():
    cfg = _make_cfg()
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        json={},
        status=200,
    )
    assert clod._unload_model("qwen2.5-coder:14b", cfg) is True


@resp_lib.activate
def test_unload_model_failure():
    cfg = _make_cfg()
    # First attempt fails
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        json={"error": "server error"},
        status=500,
    )
    # Retry also fails
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        json={"error": "server error"},
        status=500,
    )
    assert clod._unload_model("qwen2.5-coder:14b", cfg) is False


@resp_lib.activate
def test_unload_model_connection_error():
    cfg = _make_cfg()
    # First attempt connection error
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        body=ConnectionError("refused"),
    )
    # Retry also connection error
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        body=ConnectionError("refused"),
    )
    assert clod._unload_model("qwen2.5-coder:14b", cfg) is False


# ── _verify_vram_free ────────────────────────────────────────────────────────


def test_verify_vram_free_sufficient(monkeypatch):
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070", "total_mb": 16384, "free_mb": 12000},
    )
    assert clod._verify_vram_free(4000) is True


def test_verify_vram_free_insufficient(monkeypatch):
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070", "total_mb": 16384, "free_mb": 1000},
    )
    assert clod._verify_vram_free(4000) is False


def test_verify_vram_free_no_gpu(monkeypatch):
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    assert clod._verify_vram_free(4000) is True


# ── _vram_transition_panel ───────────────────────────────────────────────────


def test_vram_transition_panel_prints_usage(monkeypatch):
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070", "total_mb": 16384, "free_mb": 8192},
    )
    fc = FakeConsole()
    clod._vram_transition_panel("Loading", fc)
    output = " ".join(fc.output)
    assert "8192" in output or "8.0" in output or "VRAM" in output


def test_vram_transition_panel_noop_no_gpu(monkeypatch):
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    fc = FakeConsole()
    clod._vram_transition_panel("Loading", fc)
    # Should not crash; output may be empty or contain a dim message
    assert True


# ── _ensure_model_ready ──────────────────────────────────────────────────────


@resp_lib.activate
def test_ensure_model_ready_already_loaded(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        json={"models": [{"name": "qwen2.5-coder:14b", "size": 8000000000}]},
        status=200,
    )
    fc = FakeConsole()
    ss = {"model": "qwen2.5-coder:14b", "cfg": cfg}
    result = clod._ensure_model_ready("qwen2.5-coder:14b", cfg, fc, ss)
    assert result is True


@resp_lib.activate
def test_ensure_model_ready_swaps_model(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    # /api/ps shows different model
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        json={"models": [{"name": "llama3.1:8b", "size": 4000000000}]},
        status=200,
    )
    # Unload call
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        json={},
        status=200,
    )
    # Warmup call (ensure_ollama_model checks availability)
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "qwen2.5-coder:14b"}]},
        status=200,
    )
    # warmup_ollama_model POST
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        json={"message": {"content": ""}},
        status=200,
    )

    fc = FakeConsole()
    fc._input_response = "y"
    ss = {"model": "llama3.1:8b", "cfg": cfg}
    result = clod._ensure_model_ready("qwen2.5-coder:14b", cfg, fc, ss)
    assert result is True
    assert ss["model"] == "qwen2.5-coder:14b"


@resp_lib.activate
def test_ensure_model_ready_user_declines(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    # /api/ps shows different model
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        json={"models": [{"name": "llama3.1:8b", "size": 4000000000}]},
        status=200,
    )

    fc = FakeConsole()
    fc._input_response = "n"
    ss = {"model": "llama3.1:8b", "cfg": cfg}
    result = clod._ensure_model_ready("qwen2.5-coder:14b", cfg, fc, ss)
    assert result is False
    # No unload call should have been made (only /api/ps was called)
    assert len(resp_lib.calls) == 1  # only the /api/ps call


# ── _prepare_for_gpu_service ─────────────────────────────────────────────────


@resp_lib.activate
def test_prepare_for_gpu_service_unloads_all(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    # Stub out subprocess for docker compose
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    # Stub health to show service healthy
    monkeypatch.setattr(clod, "_check_service_health", lambda cfg: {"stable-diffusion": True})

    # /api/ps shows two models
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        json={
            "models": [
                {"name": "qwen2.5-coder:14b", "size": 8000000000},
                {"name": "llama3.1:8b", "size": 4000000000},
            ]
        },
        status=200,
    )
    # Unload calls for each model
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        json={},
        status=200,
    )
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        json={},
        status=200,
    )

    fc = FakeConsole()
    ss = {"model": "qwen2.5-coder:14b", "cfg": cfg}
    result = clod._prepare_for_gpu_service("stable-diffusion", cfg, fc, ss)
    assert result is True
    # Both models should have been unloaded (2 POST calls)
    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"]
    assert len(post_calls) == 2


@resp_lib.activate
def test_prepare_for_gpu_service_saves_prev_model(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr(clod, "_check_service_health", lambda cfg: {"stable-diffusion": True})

    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        json={"models": [{"name": "qwen2.5-coder:14b", "size": 8000000000}]},
        status=200,
    )
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        json={},
        status=200,
    )

    fc = FakeConsole()
    ss = {"model": "qwen2.5-coder:14b", "cfg": cfg}
    clod._prepare_for_gpu_service("stable-diffusion", cfg, fc, ss)
    assert ss.get("_prev_model") == "qwen2.5-coder:14b"


@resp_lib.activate
def test_prepare_for_gpu_service_noop_if_empty(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr(clod, "_check_service_health", lambda cfg: {"stable-diffusion": True})

    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        json={"models": []},
        status=200,
    )

    fc = FakeConsole()
    ss = {"model": "qwen2.5-coder:14b", "cfg": cfg}
    result = clod._prepare_for_gpu_service("stable-diffusion", cfg, fc, ss)
    assert result is True
    # No unload calls
    post_calls = [c for c in resp_lib.calls if c.request.method == "POST"]
    assert len(post_calls) == 0


@resp_lib.activate
def test_prepare_for_gpu_service_starts_service(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    docker_calls = []

    def fake_subprocess_run(*args, **kwargs):
        docker_calls.append(args[0] if args else kwargs.get("args"))
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("subprocess.run", fake_subprocess_run)

    health_calls = []

    def fake_health(cfg):
        health_calls.append(1)
        return {"stable-diffusion": True}

    monkeypatch.setattr(clod, "_check_service_health", fake_health)

    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/ps",
        json={"models": [{"name": "qwen2.5-coder:14b", "size": 8000000000}]},
        status=200,
    )
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/generate",
        json={},
        status=200,
    )

    fc = FakeConsole()
    ss = {"model": "qwen2.5-coder:14b", "cfg": cfg}
    result = clod._prepare_for_gpu_service("stable-diffusion", cfg, fc, ss)
    assert result is True
    # Docker compose should have been called
    assert len(docker_calls) >= 1
    # Health should have been polled
    assert len(health_calls) >= 1


# ── _restore_after_gpu_service ───────────────────────────────────────────────


@resp_lib.activate
def test_restore_after_gpu_service_reload_yes(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)

    warmup_calls = []

    def fake_warmup(model, cfg):
        warmup_calls.append(model)

    monkeypatch.setattr(clod, "warmup_ollama_model", fake_warmup)

    fc = FakeConsole()
    fc._input_response = "y"
    ss = {"model": "llama3.1:8b", "_prev_model": "qwen2.5-coder:14b", "cfg": cfg}
    result = clod._restore_after_gpu_service(cfg, fc, ss)
    assert result is True
    assert warmup_calls == ["qwen2.5-coder:14b"]
    assert "_prev_model" not in ss
    assert ss["model"] == "qwen2.5-coder:14b"


def test_restore_after_gpu_service_reload_no(monkeypatch):
    cfg = _make_cfg()
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)

    warmup_calls = []
    monkeypatch.setattr(clod, "warmup_ollama_model", lambda m, c: warmup_calls.append(m))

    fc = FakeConsole()
    fc._input_response = "n"
    ss = {"model": "llama3.1:8b", "_prev_model": "qwen2.5-coder:14b", "cfg": cfg}
    result = clod._restore_after_gpu_service(cfg, fc, ss)
    assert result is True
    assert warmup_calls == []
    assert "_prev_model" not in ss


def test_restore_after_gpu_service_noop_no_prev():
    cfg = _make_cfg()
    fc = FakeConsole()
    ss = {"model": "qwen2.5-coder:14b", "cfg": cfg}
    result = clod._restore_after_gpu_service(cfg, fc, ss)
    assert result is True
    # No crash, no prompt


# ── docker-compose.yml env config ────────────────────────────────────────────


def test_env_config():
    """Verify OLLAMA_MAX_LOADED_MODELS=1 is present in docker-compose.yml."""
    compose_path = pathlib.Path(__file__).parent.parent.parent / "docker-compose.yml"
    content = compose_path.read_text(encoding="utf-8")
    assert "OLLAMA_MAX_LOADED_MODELS" in content
    # Should default to 1
    assert "OLLAMA_MAX_LOADED_MODELS" in content
    # Verify it's set (the env var reference or literal 1)
    import re

    match = re.search(r"OLLAMA_MAX_LOADED_MODELS.*?[=:].*?1", content)
    assert match is not None, "OLLAMA_MAX_LOADED_MODELS should default to 1"
