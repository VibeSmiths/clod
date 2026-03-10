"""
Unit tests for video generation and docker orchestration functions.

Covers: _craft_video_prompt, _build_video_workflow, _generate_video,
        _download_comfyui_output, _ensure_generation_service, _silent_restore_model
"""

import os
import sys
import pathlib
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import responses as resp_lib
from unittest.mock import patch, MagicMock

import clod

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_console(monkeypatch):
    """Console stub with controllable input()."""
    import io, contextlib
    from rich.console import Console as _RC

    class _FC:
        def __init__(self):
            self._real = _RC(file=io.StringIO(), force_terminal=True, width=80)
            self._input_value = ""

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __enter__(self):
            return self._real.__enter__()

        def __exit__(self, *args):
            return self._real.__exit__(*args)

        def print(self, *a, **kw):
            pass

        def input(self, *a, **kw):
            return self._input_value

        def status(self, *a, **kw):
            return contextlib.nullcontext()

    fc = _FC()
    monkeypatch.setattr(clod, "console", fc)
    return fc


@pytest.fixture
def mock_cfg():
    return {
        "ollama_url": "http://localhost:11434",
        "default_model": "qwen2.5-coder:14b",
        "comfyui_output_dir": ".",
    }


@pytest.fixture
def mock_session_state(mock_cfg):
    return {
        "model": "qwen2.5-coder:14b",
        "cfg": mock_cfg,
        "offline": False,
        "intent_enabled": True,
    }


# ── _craft_video_prompt ──────────────────────────────────────────────────────


@resp_lib.activate
def test_craft_video_prompt_returns_optimized(mock_cfg):
    """Mock Ollama /api/chat, verify _craft_video_prompt returns a string prompt."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        json={
            "message": {
                "content": "A fluffy cat dancing gracefully, smooth cinematic motion, soft lighting, 4K"
            }
        },
        status=200,
    )
    result = clod._craft_video_prompt("a cat dancing", mock_cfg)
    assert isinstance(result, str)
    assert "cat" in result.lower()


@resp_lib.activate
def test_craft_video_prompt_network_error(mock_cfg):
    """Network error -> returns original user input as fallback."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        body=ConnectionError("fail"),
    )
    result = clod._craft_video_prompt("a dog running", mock_cfg)
    assert result == "a dog running"


# ── _build_video_workflow ────────────────────────────────────────────────────


def test_build_video_workflow_contains_prompt():
    """_build_video_workflow(prompt) returns dict with prompt embedded."""
    wf = clod._build_video_workflow("sunset over ocean, cinematic")
    assert isinstance(wf, dict)
    # The prompt must appear somewhere in the workflow values
    wf_str = str(wf)
    assert "sunset over ocean" in wf_str


# ── _generate_video ──────────────────────────────────────────────────────────


@resp_lib.activate
def test_generate_video_success(fake_console, mock_cfg, tmp_path):
    """POST /prompt -> poll /history -> download /view -> file saved."""
    mock_cfg["comfyui_output_dir"] = str(tmp_path)

    # Queue response
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:8188/prompt",
        json={"prompt_id": "abc123"},
        status=200,
    )

    # History response (complete)
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8188/history/abc123",
        json={
            "abc123": {
                "outputs": {
                    "9": {
                        "gifs": [
                            {
                                "filename": "output.mp4",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
                }
            }
        },
        status=200,
    )

    # /view download response
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8188/view",
        body=b"\x00\x00\x00\x1cftypisom",  # fake mp4 bytes
        status=200,
    )

    result = clod._generate_video("sunset prompt", mock_cfg, fake_console)
    assert result is not None
    assert os.path.exists(result)


@resp_lib.activate
def test_generate_video_queue_error(fake_console, mock_cfg):
    """POST /prompt fails -> returns None."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:8188/prompt",
        json={"error": "bad workflow"},
        status=500,
    )

    result = clod._generate_video("test prompt", mock_cfg, fake_console)
    assert result is None


@resp_lib.activate
def test_generate_video_timeout(fake_console, mock_cfg):
    """History never shows completion within deadline -> returns None."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:8188/prompt",
        json={"prompt_id": "xyz789"},
        status=200,
    )

    # History always returns empty (not complete)
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8188/history/xyz789",
        json={},
        status=200,
    )

    # Patch time to make timeout immediate
    with patch("clod.time") as mock_time:
        call_count = [0]

        def fake_time():
            call_count[0] += 1
            # First call: start time, subsequent calls: past deadline
            if call_count[0] <= 1:
                return 1000.0
            return 2000.0  # way past any deadline

        mock_time.time = fake_time
        mock_time.sleep = lambda x: None

        result = clod._generate_video("test prompt", mock_cfg, fake_console)
    assert result is None


# ── _download_comfyui_output ─────────────────────────────────────────────────


@resp_lib.activate
def test_download_comfyui_output_success(fake_console, mock_cfg, tmp_path):
    """Mock GET /view -> file bytes saved correctly."""
    mock_cfg["comfyui_output_dir"] = str(tmp_path)

    resp_lib.add(
        resp_lib.GET,
        "http://localhost:8188/view",
        body=b"fake-video-content-bytes",
        status=200,
    )

    item = {"filename": "video.mp4", "subfolder": "", "type": "output"}
    result = clod._download_comfyui_output(item, mock_cfg, fake_console)
    assert result is not None
    assert os.path.exists(result)
    with open(result, "rb") as f:
        assert f.read() == b"fake-video-content-bytes"


# ── _ensure_generation_service ───────────────────────────────────────────────


def test_ensure_generation_service_image_already_running(
    fake_console, mock_cfg, mock_session_state
):
    """query_comfyui_running True -> no service start, returns True."""
    with patch.object(clod, "query_comfyui_running", return_value=True):
        result = clod._ensure_generation_service(
            "image_gen", mock_cfg, fake_console, mock_session_state
        )
    assert result is True


def test_ensure_generation_service_image_not_running(fake_console, mock_cfg, mock_session_state):
    """query_comfyui_running False -> calls _prepare_for_gpu_service."""
    with (
        patch.object(clod, "query_comfyui_running", return_value=False),
        patch.object(clod, "_prepare_for_gpu_service", return_value=True) as mock_prep,
    ):
        result = clod._ensure_generation_service(
            "image_gen", mock_cfg, fake_console, mock_session_state
        )
    assert result is True
    mock_prep.assert_called_once_with(
        "stable-diffusion", mock_cfg, fake_console, mock_session_state
    )


def test_ensure_generation_service_video_needs_switch(fake_console, mock_cfg, mock_session_state):
    """video_gen, A1111 running but ComfyUI not -> confirm + switch profile."""
    fake_console._input_value = "y"

    with (
        patch.object(clod, "query_video_running", return_value=False),
        patch.object(clod, "query_comfyui_running", return_value=True),
        patch.object(clod, "sd_switch_mode", return_value=(True, "ok")) as mock_switch,
        patch.object(clod, "_prepare_for_gpu_service", return_value=True) as mock_prep,
    ):
        result = clod._ensure_generation_service(
            "video_gen", mock_cfg, fake_console, mock_session_state
        )
    assert result is True
    mock_switch.assert_called_once_with("video", mock_cfg)
    mock_prep.assert_called_once()


def test_ensure_generation_service_video_switch_declined(
    fake_console, mock_cfg, mock_session_state
):
    """User declines confirmation -> returns False."""
    fake_console._input_value = "n"

    with (
        patch.object(clod, "query_video_running", return_value=False),
        patch.object(clod, "query_comfyui_running", return_value=True),
    ):
        result = clod._ensure_generation_service(
            "video_gen", mock_cfg, fake_console, mock_session_state
        )
    assert result is False


def test_ensure_generation_service_detects_profile_mismatch(
    fake_console, mock_cfg, mock_session_state
):
    """Intent video_gen but image profile running -> triggers switch (DOCK-01)."""
    fake_console._input_value = "y"

    with (
        patch.object(clod, "query_video_running", return_value=False),
        patch.object(clod, "query_comfyui_running", return_value=True),
        patch.object(clod, "sd_switch_mode", return_value=(True, "switched")) as mock_sw,
        patch.object(clod, "_prepare_for_gpu_service", return_value=True),
    ):
        result = clod._ensure_generation_service(
            "video_gen", mock_cfg, fake_console, mock_session_state
        )
    assert result is True
    # Verifies DOCK-01: auto-detected that image profile was running when video needed
    mock_sw.assert_called_once_with("video", mock_cfg)


# ── _silent_restore_model ────────────────────────────────────────────────────


def test_silent_restore_model_reloads(fake_console, mock_cfg, mock_session_state):
    """_silent_restore_model loads _prev_model without prompting."""
    mock_session_state["_prev_model"] = "qwen2.5-coder:14b"

    with patch.object(clod, "warmup_ollama_model") as mock_warmup:
        clod._silent_restore_model(mock_cfg, fake_console, mock_session_state)

    mock_warmup.assert_called_once_with("qwen2.5-coder:14b", mock_cfg)
    assert mock_session_state["model"] == "qwen2.5-coder:14b"
    assert "_prev_model" not in mock_session_state


def test_silent_restore_model_no_prev(fake_console, mock_cfg, mock_session_state):
    """No _prev_model in session_state -> no-op."""
    with patch.object(clod, "warmup_ollama_model") as mock_warmup:
        clod._silent_restore_model(mock_cfg, fake_console, mock_session_state)

    mock_warmup.assert_not_called()
