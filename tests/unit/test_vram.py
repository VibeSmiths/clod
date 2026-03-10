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
        self.raw_output = []
        self._input_response = ""

    def print(self, *args, **kwargs):
        obj = args[0] if args else ""
        self.raw_output.append(obj)
        # For Panel objects, extract the renderable text
        if hasattr(obj, "renderable"):
            self.output.append(str(obj.renderable))
        else:
            self.output.append(str(obj))

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


# ── handle_slash VRAM wiring ────────────────────────────────────────────────

from clod import handle_slash, TokenBudget


def _make_slash_state(cfg=None):
    """Return a fresh session_state for handle_slash tests."""
    if cfg is None:
        cfg = _make_cfg()
    return {
        "model": "qwen2.5-coder:14b",
        "pipeline": None,
        "tools_on": False,
        "system": None,
        "cfg": cfg,
        "budget": TokenBudget(10000),
        "offline": False,
    }


# -- Test 1: /model calls _ensure_model_ready for non-cloud models --


def test_model_calls_ensure_model_ready(monkeypatch):
    """'/model deepseek-r1:14b' calls _ensure_model_ready, not warmup_ollama_model."""
    ensure_calls = []

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        ensure_calls.append({"target": target, "confirm": confirm})
        session_state["model"] = target
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    monkeypatch.setattr(clod, "console", FakeConsole())

    state = _make_slash_state()
    handle_slash("/model deepseek-r1:14b", state, [])

    assert len(ensure_calls) == 1
    assert ensure_calls[0]["target"] == "deepseek-r1:14b"
    assert ensure_calls[0]["confirm"] is True


# -- Test 2: /model sets session_state["model"] when _ensure_model_ready returns True --


def test_model_sets_state_on_ensure_true(monkeypatch):
    """'/model X' sets model and clears pipeline when _ensure_model_ready returns True."""

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        session_state["model"] = target
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    monkeypatch.setattr(clod, "console", FakeConsole())

    state = _make_slash_state()
    state["pipeline"] = "code_review"
    handle_slash("/model deepseek-r1:14b", state, [])

    assert state["model"] == "deepseek-r1:14b"
    assert state["pipeline"] is None


# -- Test 3: /model does NOT switch when _ensure_model_ready returns False --


def test_model_no_switch_on_ensure_false(monkeypatch):
    """'/model X' does not change model when _ensure_model_ready returns False."""

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        return False

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    fc = FakeConsole()
    monkeypatch.setattr(clod, "console", fc)

    state = _make_slash_state()
    state["pipeline"] = "code_review"
    handle_slash("/model deepseek-r1:14b", state, [])

    assert state["model"] == "qwen2.5-coder:14b"  # unchanged
    assert state["pipeline"] == "code_review"  # unchanged
    assert any("cancelled" in s.lower() for s in fc.output)


# -- Test 4: /gpu use calls _ensure_model_ready with confirm=False --


def test_gpu_use_calls_ensure_model_ready(monkeypatch):
    """/gpu use calls _ensure_model_ready with confirm=False."""
    ensure_calls = []

    def fake_ensure(target, cfg, console_obj, session_state, confirm=True):
        ensure_calls.append({"target": target, "confirm": confirm})
        session_state["model"] = target
        return True

    monkeypatch.setattr(clod, "_ensure_model_ready", fake_ensure)
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070 Ti", "total_mb": 16384, "free_mb": 10000},
    )
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    monkeypatch.setattr(clod, "console", FakeConsole())

    state = _make_slash_state()
    handle_slash("/gpu use", state, [])

    assert len(ensure_calls) == 1
    assert ensure_calls[0]["confirm"] is False


# -- Test 5: /sd image|video unloads models before sd_switch_mode --


def test_sd_video_unloads_before_switch(monkeypatch):
    """/sd video unloads loaded models before calling sd_switch_mode."""
    call_order = []

    def fake_get_loaded(cfg):
        call_order.append("get_loaded")
        return [{"name": "qwen2.5-coder:14b"}]

    def fake_unload(name, cfg):
        call_order.append(f"unload:{name}")
        return True

    def fake_switch(mode, cfg):
        call_order.append("sd_switch_mode")
        return (True, "ok")

    monkeypatch.setattr(clod, "_get_loaded_models", fake_get_loaded)
    monkeypatch.setattr(clod, "_unload_model", fake_unload)
    monkeypatch.setattr(clod, "_vram_transition_panel", lambda phase, c: call_order.append("panel"))
    monkeypatch.setattr(clod, "_verify_vram_free", lambda min_free_mb=4000: True)
    monkeypatch.setattr(clod, "sd_switch_mode", fake_switch)
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: None)
    monkeypatch.setattr(clod, "console", FakeConsole())

    state = _make_slash_state()
    state["sd_mode"] = "image"
    handle_slash("/sd video", state, [])

    # Unload must happen before sd_switch_mode
    assert "get_loaded" in call_order
    assert "unload:qwen2.5-coder:14b" in call_order
    sd_idx = call_order.index("sd_switch_mode")
    unload_idx = call_order.index("unload:qwen2.5-coder:14b")
    assert unload_idx < sd_idx


# -- Test 6: /sd image|video calls _verify_vram_free after unload, before switch --


def test_sd_image_verifies_vram_after_unload(monkeypatch):
    """/sd image calls _verify_vram_free after unloading and before sd_switch_mode."""
    call_order = []

    def fake_get_loaded(cfg):
        call_order.append("get_loaded")
        return [{"name": "llama3.1:8b"}]

    def fake_unload(name, cfg):
        call_order.append("unload")
        return True

    def fake_verify(min_free_mb=4000):
        call_order.append("verify_vram")
        return True

    def fake_switch(mode, cfg):
        call_order.append("sd_switch_mode")
        return (True, "ok")

    monkeypatch.setattr(clod, "_get_loaded_models", fake_get_loaded)
    monkeypatch.setattr(clod, "_unload_model", fake_unload)
    monkeypatch.setattr(clod, "_vram_transition_panel", lambda phase, c: None)
    monkeypatch.setattr(clod, "_verify_vram_free", fake_verify)
    monkeypatch.setattr(clod, "sd_switch_mode", fake_switch)
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: None)
    monkeypatch.setattr(clod, "console", FakeConsole())

    state = _make_slash_state()
    state["sd_mode"] = "video"
    handle_slash("/sd image", state, [])

    # verify_vram must be after unload and before sd_switch_mode
    assert "verify_vram" in call_order
    verify_idx = call_order.index("verify_vram")
    unload_idx = call_order.index("unload")
    sd_idx = call_order.index("sd_switch_mode")
    assert unload_idx < verify_idx < sd_idx


# -- Test 7: /sd start unloads and verifies VRAM before sd_switch_mode --


def test_sd_start_unloads_and_verifies(monkeypatch):
    """/sd start unloads models and verifies VRAM before sd_switch_mode."""
    call_order = []

    def fake_get_loaded(cfg):
        call_order.append("get_loaded")
        return [{"name": "qwen2.5-coder:14b"}]

    def fake_unload(name, cfg):
        call_order.append("unload")
        return True

    def fake_verify(min_free_mb=4000):
        call_order.append("verify_vram")
        return True

    def fake_switch(mode, cfg):
        call_order.append("sd_switch_mode")
        return (True, "ok")

    monkeypatch.setattr(clod, "_get_loaded_models", fake_get_loaded)
    monkeypatch.setattr(clod, "_unload_model", fake_unload)
    monkeypatch.setattr(clod, "_vram_transition_panel", lambda phase, c: None)
    monkeypatch.setattr(clod, "_verify_vram_free", fake_verify)
    monkeypatch.setattr(clod, "sd_switch_mode", fake_switch)
    monkeypatch.setattr(clod, "console", FakeConsole())

    state = _make_slash_state()
    state["sd_mode"] = "image"
    handle_slash("/sd start", state, [])

    assert "get_loaded" in call_order
    assert "verify_vram" in call_order
    assert "sd_switch_mode" in call_order
    verify_idx = call_order.index("verify_vram")
    sd_idx = call_order.index("sd_switch_mode")
    assert verify_idx < sd_idx


# -- Test 8: /sd stop calls _restore_after_gpu_service --


def test_sd_stop_calls_restore(monkeypatch):
    """/sd stop calls _restore_after_gpu_service after stopping services."""
    restore_calls = []

    def fake_restore(cfg, console_obj, session_state):
        restore_calls.append(True)
        return True

    monkeypatch.setattr(clod, "query_comfyui_running", lambda: True)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "comfyui_docker_action", lambda action: (True, "ok"))
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "_restore_after_gpu_service", fake_restore)
    monkeypatch.setattr(clod, "console", FakeConsole())

    state = _make_slash_state()
    handle_slash("/sd stop", state, [])

    assert len(restore_calls) == 1
