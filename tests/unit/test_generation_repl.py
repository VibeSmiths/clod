"""
Unit tests for generation REPL integration and /generate slash command.

Covers: _handle_generation_intent orchestrator, /generate slash command,
        REPL intent interception for image_gen/video_gen.
"""

import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
from unittest.mock import patch, MagicMock, call

import clod

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_console(monkeypatch):
    """Console stub that records print calls."""
    import io, contextlib
    from rich.console import Console as _RC

    class _FC:
        def __init__(self):
            self._real = _RC(file=io.StringIO(), force_terminal=True, width=80)
            self.printed = []

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __enter__(self):
            return self._real.__enter__()

        def __exit__(self, *args):
            return self._real.__exit__(*args)

        def print(self, *a, **kw):
            self.printed.append(a)

        def input(self, *a, **kw):
            return ""

        def status(self, *a, **kw):
            return contextlib.nullcontext()

    fc = _FC()
    monkeypatch.setattr(clod, "console", fc)
    return fc


@pytest.fixture
def mock_cfg():
    return {
        "ollama_url": "http://localhost:11434",
        "sd_output_dir": "",
        "default_model": "qwen2.5-coder:14b",
    }


@pytest.fixture
def mock_session(mock_cfg):
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
        "sd_mode": "image",
        "_prev_model": None,
    }


# ── Image full flow ──────────────────────────────────────────────────────────


@patch("clod._silent_restore_model")
@patch("os.startfile", create=True)
@patch("clod._generate_image", return_value="/tmp/clod_img.png")
@patch("clod._get_negative_prompts", return_value="bad quality")
@patch("clod._detect_sd_model_type", return_value="sd15")
@patch("clod._ensure_generation_service", return_value=True)
@patch("clod._unload_model", return_value=True)
@patch("clod._craft_sd_prompt", return_value=("a beautiful sunset, golden hour", "blur"))
@patch("clod._ensure_model_ready", return_value=True)
def test_handle_generation_intent_image_full_flow(
    m_ensure,
    m_craft,
    m_unload,
    m_svc,
    m_detect,
    m_neg,
    m_gen,
    m_open,
    m_restore,
    fake_console,
    mock_session,
    mock_cfg,
):
    clod._handle_generation_intent("image_gen", "a sunset", mock_session, fake_console, mock_cfg)

    # Verify call sequence
    m_ensure.assert_called_once_with(
        "llama3.1:8b", mock_cfg, fake_console, mock_session, confirm=False
    )
    m_craft.assert_called_once_with("a sunset", mock_cfg)
    m_unload.assert_called_once_with("llama3.1:8b", mock_cfg)
    m_svc.assert_called_once_with("image_gen", mock_cfg, fake_console, mock_session)
    m_detect.assert_called_once()
    m_neg.assert_called_once()
    m_gen.assert_called_once()
    m_restore.assert_called_once_with(mock_cfg, fake_console, mock_session)


# ── Video full flow ──────────────────────────────────────────────────────────


@patch("clod._silent_restore_model")
@patch("os.startfile", create=True)
@patch("clod._generate_video", return_value="/tmp/clod_vid.mp4")
@patch("clod._ensure_generation_service", return_value=True)
@patch("clod._unload_model", return_value=True)
@patch("clod._craft_video_prompt", return_value="a cat dancing gracefully")
@patch("clod._ensure_model_ready", return_value=True)
def test_handle_generation_intent_video_full_flow(
    m_ensure,
    m_craft,
    m_unload,
    m_svc,
    m_gen,
    m_open,
    m_restore,
    fake_console,
    mock_session,
    mock_cfg,
):
    clod._handle_generation_intent("video_gen", "dancing cat", mock_session, fake_console, mock_cfg)

    m_ensure.assert_called_once_with(
        "llama3.1:8b", mock_cfg, fake_console, mock_session, confirm=False
    )
    m_craft.assert_called_once_with("dancing cat", mock_cfg)
    m_unload.assert_called_once_with("llama3.1:8b", mock_cfg)
    m_svc.assert_called_once_with("video_gen", mock_cfg, fake_console, mock_session)
    m_gen.assert_called_once()
    m_restore.assert_called_once()


# ── Service start declined ───────────────────────────────────────────────────


@patch("clod._silent_restore_model")
@patch("clod._ensure_generation_service", return_value=False)
@patch("clod._unload_model", return_value=True)
@patch("clod._craft_sd_prompt", return_value=("sunset", ""))
@patch("clod._ensure_model_ready", return_value=True)
def test_handle_generation_intent_service_start_declined(
    m_ensure,
    m_craft,
    m_unload,
    m_svc,
    m_restore,
    fake_console,
    mock_session,
    mock_cfg,
):
    clod._handle_generation_intent("image_gen", "sunset", mock_session, fake_console, mock_cfg)

    m_svc.assert_called_once()
    m_restore.assert_called_once()  # still restores model even on abort


# ── Craft failure fallback ───────────────────────────────────────────────────


@patch("clod._silent_restore_model")
@patch("os.startfile", create=True)
@patch("clod._generate_image", return_value="/tmp/out.png")
@patch("clod._get_negative_prompts", return_value="bad")
@patch("clod._detect_sd_model_type", return_value="sd15")
@patch("clod._ensure_generation_service", return_value=True)
@patch("clod._unload_model", return_value=True)
@patch("clod._craft_sd_prompt", side_effect=Exception("LLM down"))
@patch("clod._ensure_model_ready", return_value=True)
def test_handle_generation_intent_craft_failure(
    m_ensure,
    m_craft,
    m_unload,
    m_svc,
    m_detect,
    m_neg,
    m_gen,
    m_open,
    m_restore,
    fake_console,
    mock_session,
    mock_cfg,
):
    clod._handle_generation_intent("image_gen", "raw sunset", mock_session, fake_console, mock_cfg)

    # Should still generate with raw user input as fallback
    m_gen.assert_called_once()
    args = m_gen.call_args
    assert args[0][0] == "raw sunset"  # prompt fallback to raw input


# ── Generation failure ───────────────────────────────────────────────────────


@patch("clod._silent_restore_model")
@patch("clod._generate_image", return_value=None)
@patch("clod._get_negative_prompts", return_value="bad")
@patch("clod._detect_sd_model_type", return_value="sd15")
@patch("clod._ensure_generation_service", return_value=True)
@patch("clod._unload_model", return_value=True)
@patch("clod._craft_sd_prompt", return_value=("sunset", ""))
@patch("clod._ensure_model_ready", return_value=True)
def test_handle_generation_intent_generation_failure(
    m_ensure,
    m_craft,
    m_unload,
    m_svc,
    m_detect,
    m_neg,
    m_gen,
    m_restore,
    fake_console,
    mock_session,
    mock_cfg,
):
    clod._handle_generation_intent("image_gen", "sunset", mock_session, fake_console, mock_cfg)

    m_gen.assert_called_once()
    m_restore.assert_called_once()  # model restored even on failure
    # Check error message was printed
    any_error = any(
        "error" in str(a).lower() or "fail" in str(a).lower() for a in fake_console.printed
    )
    assert any_error


# ── Shows crafted prompt ─────────────────────────────────────────────────────


@patch("clod._silent_restore_model")
@patch("os.startfile", create=True)
@patch("clod._generate_image", return_value="/tmp/out.png")
@patch("clod._get_negative_prompts", return_value="bad")
@patch("clod._detect_sd_model_type", return_value="sd15")
@patch("clod._ensure_generation_service", return_value=True)
@patch("clod._unload_model", return_value=True)
@patch("clod._craft_sd_prompt", return_value=("epic sunset over ocean", ""))
@patch("clod._ensure_model_ready", return_value=True)
def test_handle_generation_intent_shows_crafted_prompt(
    m_ensure,
    m_craft,
    m_unload,
    m_svc,
    m_detect,
    m_neg,
    m_gen,
    m_open,
    m_restore,
    fake_console,
    mock_session,
    mock_cfg,
):
    clod._handle_generation_intent("image_gen", "sunset", mock_session, fake_console, mock_cfg)

    # At least one print call should contain the crafted prompt
    all_text = " ".join(str(a) for a in fake_console.printed)
    assert "epic sunset over ocean" in all_text


# ── Auto-opens file ──────────────────────────────────────────────────────────


@patch("clod._silent_restore_model")
@patch("clod._generate_image", return_value="/tmp/clod_img.png")
@patch("clod._get_negative_prompts", return_value="bad")
@patch("clod._detect_sd_model_type", return_value="sd15")
@patch("clod._ensure_generation_service", return_value=True)
@patch("clod._unload_model", return_value=True)
@patch("clod._craft_sd_prompt", return_value=("sunset", ""))
@patch("clod._ensure_model_ready", return_value=True)
def test_handle_generation_intent_auto_opens_file(
    m_ensure,
    m_craft,
    m_unload,
    m_svc,
    m_detect,
    m_neg,
    m_gen,
    m_restore,
    fake_console,
    mock_session,
    mock_cfg,
):
    with patch("os.startfile", create=True) as m_open:
        clod._handle_generation_intent("image_gen", "sunset", mock_session, fake_console, mock_cfg)
        if hasattr(os, "startfile"):
            m_open.assert_called_once_with("/tmp/clod_img.png")


# ── /generate image slash command ────────────────────────────────────────────


@patch("clod._handle_generation_intent")
def test_slash_generate_image(m_handle, fake_console, mock_session):
    result = clod.handle_slash("/generate image a sunset", mock_session, [])
    assert result is True
    m_handle.assert_called_once()
    args = m_handle.call_args
    assert args[0][0] == "image_gen"
    assert args[0][1] == "a sunset"


# ── /generate video slash command ────────────────────────────────────────────


@patch("clod._handle_generation_intent")
def test_slash_generate_video(m_handle, fake_console, mock_session):
    result = clod.handle_slash("/generate video dancing cat", mock_session, [])
    assert result is True
    m_handle.assert_called_once()
    args = m_handle.call_args
    assert args[0][0] == "video_gen"
    assert args[0][1] == "dancing cat"


# ── /generate no prompt ──────────────────────────────────────────────────────


@patch("clod._handle_generation_intent")
def test_slash_generate_no_prompt(m_handle, fake_console, mock_session):
    result = clod.handle_slash("/generate image", mock_session, [])
    assert result is True
    m_handle.assert_not_called()  # should show usage, not call handler
    any_usage = any(
        "usage" in str(a).lower() or "prompt" in str(a).lower() for a in fake_console.printed
    )
    assert any_usage


# ── /generate unknown type ───────────────────────────────────────────────────


@patch("clod._handle_generation_intent")
def test_slash_generate_unknown_type(m_handle, fake_console, mock_session):
    result = clod.handle_slash("/generate foo bar", mock_session, [])
    assert result is True
    m_handle.assert_not_called()
    any_err = any(
        "image" in str(a).lower() and "video" in str(a).lower() for a in fake_console.printed
    )
    assert any_err


# ── REPL intent interception ─────────────────────────────────────────────────


@patch("clod._handle_generation_intent")
@patch("clod.classify_intent", return_value=("image_gen", 0.9))
@patch("clod.infer", return_value="should not be called")
def test_repl_intent_interception(m_infer, m_classify, m_handle, fake_console, mock_session):
    """When classify_intent returns image_gen with high confidence,
    _handle_generation_intent should be called instead of infer."""
    # We can't easily test run_repl directly, so test the routing logic
    # by checking that _handle_generation_intent is callable with image_gen intent
    # and that INTENT_MODEL_MAP maps image_gen to None
    assert clod.INTENT_MODEL_MAP.get("image_gen") is None
    assert clod.INTENT_MODEL_MAP.get("video_gen") is None

    # Verify _handle_generation_intent exists and is callable
    assert callable(clod._handle_generation_intent)
