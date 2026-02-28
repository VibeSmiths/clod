"""
Tests for Ollama model-management functions:
  ollama_local_models, ollama_model_available, ensure_ollama_model,
  warmup_ollama_model, query_gpu_vram, recommend_model_for_vram
"""

import subprocess
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


# ── query_gpu_vram ────────────────────────────────────────────────────────────


class MockResult:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_query_gpu_vram_success(monkeypatch):
    """Parses nvidia-smi CSV output into name/total_mb/free_mb."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: MockResult(returncode=0, stdout="RTX 4070 Ti SUPER, 16376, 6000\n"),
    )
    info = clod.query_gpu_vram()
    assert info["name"] == "RTX 4070 Ti SUPER"
    assert info["total_mb"] == 16376
    assert info["free_mb"] == 6000


def test_query_gpu_vram_unavailable(monkeypatch):
    """Returns None when nvidia-smi is not found."""
    def _raise(*a, **k):
        raise FileNotFoundError()
    monkeypatch.setattr(subprocess, "run", _raise)
    assert clod.query_gpu_vram() is None


def test_query_gpu_vram_nonzero_returncode(monkeypatch):
    """Returns None when nvidia-smi exits with non-zero code."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: MockResult(returncode=6, stdout=""),
    )
    assert clod.query_gpu_vram() is None


# ── recommend_model_for_vram ──────────────────────────────────────────────────


def test_recommend_model_16gb():
    assert clod.recommend_model_for_vram(16_376) == "qwen2.5-coder:14b"


def test_recommend_model_24gb():
    assert clod.recommend_model_for_vram(24_576) == "qwen2.5-coder:32b-instruct-q4_K_M"


def test_recommend_model_8gb():
    assert clod.recommend_model_for_vram(8_192) == "llama3.1:8b"


def test_recommend_model_tiny():
    assert clod.recommend_model_for_vram(2_000) is None


# ── query_system_info ─────────────────────────────────────────────────────────


def test_query_system_info_returns_dict():
    """query_system_info always returns a dict with at least cpu_name and cpu_logical."""
    info = clod.query_system_info()
    assert isinstance(info, dict)
    assert "cpu_name" in info
    assert info.get("cpu_logical", 0) >= 1


def test_query_system_info_ram_with_psutil():
    """When psutil is available, ram_total_mb is non-zero."""
    if clod.HAS_PSUTIL:
        info = clod.query_system_info()
        assert info.get("ram_total_mb", 0) > 0


# ── query_comfyui_running ─────────────────────────────────────────────────────


def test_query_comfyui_running_true(monkeypatch):
    """Returns True when localhost:7860 (AUTOMATIC1111) responds with HTTP 2xx."""
    class _Resp:
        status_code = 200

    monkeypatch.setattr(clod.requests, "get", lambda *a, **k: _Resp())
    assert clod.query_comfyui_running() is True


def test_query_comfyui_running_connection_error(monkeypatch):
    """Returns False when the connection is refused."""
    monkeypatch.setattr(
        clod.requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ConnectionError()),
    )
    assert clod.query_comfyui_running() is False


# ── find_comfyui_container ────────────────────────────────────────────────────


def test_find_comfyui_container_found(monkeypatch):
    """Parses container name from docker ps output."""
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: MockResult(returncode=0, stdout="comfyui\n")
    )
    assert clod.find_comfyui_container() == "comfyui"


def test_find_comfyui_container_none(monkeypatch):
    """Returns None when docker ps output is empty."""
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: MockResult(returncode=0, stdout="")
    )
    assert clod.find_comfyui_container() is None


# ── comfyui_docker_action ─────────────────────────────────────────────────────


def test_comfyui_docker_action_stop_success(monkeypatch):
    """Returns (True, message) when docker stop succeeds."""
    monkeypatch.setattr(clod, "find_comfyui_container", lambda: "comfyui")
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: MockResult(returncode=0, stdout="comfyui\n")
    )
    ok, msg = clod.comfyui_docker_action("stop")
    assert ok is True
    assert "OK" in msg


def test_comfyui_docker_action_no_container(monkeypatch):
    """Returns (False, message) when no container is found."""
    monkeypatch.setattr(clod, "find_comfyui_container", lambda: None)
    ok, msg = clod.comfyui_docker_action("stop")
    assert ok is False
    assert "not found" in msg


def test_comfyui_docker_action_docker_missing(monkeypatch):
    """Returns (False, message) when docker CLI is absent."""
    monkeypatch.setattr(clod, "find_comfyui_container", lambda: "comfyui")

    def _raise(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(subprocess, "run", _raise)
    ok, msg = clod.comfyui_docker_action("stop")
    assert ok is False
    assert "docker CLI" in msg


# ── query_video_running ───────────────────────────────────────────────────────


def test_query_video_running_true(monkeypatch):
    class _Resp:
        status_code = 200
    monkeypatch.setattr(clod.requests, "get", lambda *a, **k: _Resp())
    assert clod.query_video_running() is True


def test_query_video_running_false(monkeypatch):
    monkeypatch.setattr(
        clod.requests, "get",
        lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ConnectionError()),
    )
    assert clod.query_video_running() is False


# ── update_dotenv_key ─────────────────────────────────────────────────────────


def test_update_dotenv_key_existing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nIMAGE_GENERATION_ENGINE=automatic1111\nBAZ=qux\n")
    clod.update_dotenv_key(str(env), "IMAGE_GENERATION_ENGINE", "comfyui")
    assert "IMAGE_GENERATION_ENGINE=comfyui" in env.read_text()
    assert "FOO=bar" in env.read_text()   # other keys untouched


def test_update_dotenv_key_append(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\n")
    clod.update_dotenv_key(str(env), "NEW_KEY", "value")
    assert "NEW_KEY=value" in env.read_text()
    assert "FOO=bar" in env.read_text()


def test_update_dotenv_key_missing_file():
    assert clod.update_dotenv_key("/nonexistent/.env", "K", "v") is False


# ── sd_switch_mode ────────────────────────────────────────────────────────────


def test_sd_switch_mode_missing_compose(mock_cfg):
    cfg = {**mock_cfg, "compose_file": "/nonexistent/docker-compose.yml", "dotenv_file": ""}
    ok, msg = clod.sd_switch_mode("video", cfg)
    assert ok is False
    assert "not found" in msg


def test_sd_switch_mode_invalid_mode(mock_cfg):
    ok, msg = clod.sd_switch_mode("invalid", mock_cfg)
    assert ok is False
    assert "Unknown mode" in msg
