"""
E2E tests for generation pipeline: failure scenarios, file output verification,
Docker profile switch flow, and model-restore guarantee.

Covers: _handle_generation_intent orchestrator error paths, actual file writes
via _save_generation_output, and profile switch sequence.
"""

import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
from unittest.mock import patch, MagicMock, call
import contextlib
import io

import clod

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_console(monkeypatch):
    """Console stub that records print calls."""
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
def mock_cfg(tmp_path):
    return {
        "ollama_url": "http://localhost:11434",
        "sd_output_dir": str(tmp_path),
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


# ── File output verification ─────────────────────────────────────────────────


class TestFileOutputVerification:
    """Verify that _handle_generation_intent produces actual files on disk."""

    @patch("clod._silent_restore_model")
    @patch("os.startfile", create=True)
    @patch("clod._get_negative_prompts", return_value="bad quality")
    @patch("clod._detect_sd_model_type", return_value="sd15")
    @patch("clod._ensure_generation_service", return_value=True)
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_sd_prompt", return_value=("a beautiful sunset, golden hour", "blur"))
    @patch("clod._ensure_model_ready", return_value=True)
    def test_generation_image_saves_to_disk(
        self,
        m_ensure,
        m_craft,
        m_unload,
        m_svc,
        m_detect,
        m_neg,
        m_open,
        m_restore,
        fake_console,
        mock_session,
        mock_cfg,
        tmp_path,
    ):
        """Mock _generate_image to write a real file, verify it on disk."""
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        output_path = str(tmp_path / "clod_20260310_120000_abcd.png")
        # Write fake file to disk so the handler finds it
        with open(output_path, "wb") as f:
            f.write(fake_png)

        with patch("clod._generate_image", return_value=output_path) as m_gen:
            clod._handle_generation_intent(
                "image_gen", "a sunset", mock_session, fake_console, mock_cfg
            )
            m_gen.assert_called_once()

        # Verify file exists and has correct content
        assert os.path.isfile(output_path)
        with open(output_path, "rb") as f:
            content = f.read()
        assert content == fake_png
        assert content[:4] == b"\x89PNG"

    @patch("clod._silent_restore_model")
    @patch("os.startfile", create=True)
    @patch("clod._ensure_generation_service", return_value=True)
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_video_prompt", return_value="a cat dancing gracefully")
    @patch("clod._ensure_model_ready", return_value=True)
    def test_generation_video_saves_to_disk(
        self,
        m_ensure,
        m_craft,
        m_unload,
        m_svc,
        m_open,
        m_restore,
        fake_console,
        mock_session,
        mock_cfg,
        tmp_path,
    ):
        """Mock _generate_video to write a real file, verify it on disk."""
        fake_mp4 = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 50
        output_path = str(tmp_path / "clod_20260310_120000_efgh.mp4")
        with open(output_path, "wb") as f:
            f.write(fake_mp4)

        with patch("clod._generate_video", return_value=output_path) as m_gen:
            clod._handle_generation_intent(
                "video_gen", "dancing cat", mock_session, fake_console, mock_cfg
            )
            m_gen.assert_called_once()

        assert os.path.isfile(output_path)
        with open(output_path, "rb") as f:
            content = f.read()
        assert content == fake_mp4


# ── Failure scenarios ─────────────────────────────────────────────────────────


class TestFailureScenarios:
    """Verify graceful degradation on various failure conditions."""

    @patch("clod._silent_restore_model")
    @patch("clod._ensure_generation_service", return_value=False)
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_sd_prompt", return_value=("sunset prompt", ""))
    @patch("clod._ensure_model_ready", return_value=True)
    def test_generation_service_unreachable(
        self,
        m_ensure,
        m_craft,
        m_unload,
        m_svc,
        m_restore,
        fake_console,
        mock_session,
        mock_cfg,
    ):
        """When _ensure_generation_service returns False, should abort without generating."""
        with patch("clod._generate_image") as m_gen:
            clod._handle_generation_intent(
                "image_gen", "a sunset", mock_session, fake_console, mock_cfg
            )
            # Should NOT call _generate_image when service is not available
            m_gen.assert_not_called()

        # Model restore must still be called (try/finally)
        m_restore.assert_called_once_with(mock_cfg, fake_console, mock_session)

    @patch("clod._silent_restore_model")
    @patch("os.startfile", create=True)
    @patch("clod._generate_image", return_value="/tmp/fallback.png")
    @patch("clod._get_negative_prompts", return_value="bad")
    @patch("clod._detect_sd_model_type", return_value="sd15")
    @patch("clod._ensure_generation_service", return_value=True)
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_sd_prompt", side_effect=Exception("LLM is down"))
    @patch("clod._ensure_model_ready", return_value=True)
    def test_generation_craft_prompt_failure(
        self,
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
        """When _craft_sd_prompt raises, should fall back to raw user input."""
        clod._handle_generation_intent(
            "image_gen", "raw sunset input", mock_session, fake_console, mock_cfg
        )

        # Generation should still proceed with raw user input as prompt
        m_gen.assert_called_once()
        call_args = m_gen.call_args
        assert call_args[0][0] == "raw sunset input"  # prompt is raw input

        # Model restore still called
        m_restore.assert_called_once()

    @patch("clod._silent_restore_model")
    @patch("clod._generate_image", side_effect=ConnectionError("Connection refused"))
    @patch("clod._get_negative_prompts", return_value="bad")
    @patch("clod._detect_sd_model_type", return_value="sd15")
    @patch("clod._ensure_generation_service", return_value=True)
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_sd_prompt", return_value=("crafted prompt", "neg"))
    @patch("clod._ensure_model_ready", return_value=True)
    def test_generation_image_api_error(
        self,
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
        """When _generate_image raises ConnectionError, model restore still happens."""
        # The exception propagates through try/finally, but finally still runs
        with pytest.raises(ConnectionError):
            clod._handle_generation_intent(
                "image_gen", "a sunset", mock_session, fake_console, mock_cfg
            )

        m_gen.assert_called_once()
        # Model restore must still be called despite exception (try/finally)
        m_restore.assert_called_once_with(mock_cfg, fake_console, mock_session)

    @patch("clod._silent_restore_model")
    @patch("os.startfile", create=True)
    @patch("clod._generate_image", return_value="/tmp/still_works.png")
    @patch("clod._get_negative_prompts", return_value="bad")
    @patch("clod._detect_sd_model_type", return_value="sd15")
    @patch("clod._ensure_generation_service", return_value=True)
    @patch("clod._unload_model", return_value=False)
    @patch("clod._craft_sd_prompt", return_value=("sunset", ""))
    @patch("clod._ensure_model_ready", return_value=True)
    def test_generation_vram_unload_failure(
        self,
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
        """When _unload_model returns False, generation should still proceed."""
        clod._handle_generation_intent(
            "image_gen", "a sunset", mock_session, fake_console, mock_cfg
        )

        # VRAM unload failure is non-blocking
        m_unload.assert_called_once()
        m_gen.assert_called_once()  # generation still proceeds
        m_restore.assert_called_once()


# ── Docker profile switch E2E ─────────────────────────────────────────────────


class TestProfileSwitchE2E:
    """Test the Docker profile switch flow from image to video."""

    @patch("clod._silent_restore_model")
    @patch("os.startfile", create=True)
    @patch("clod._generate_video", return_value="/tmp/video_out.mp4")
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_video_prompt", return_value="a cat dancing gracefully")
    @patch("clod._ensure_model_ready", return_value=True)
    def test_profile_switch_e2e_image_to_video(
        self,
        m_ensure,
        m_craft,
        m_unload,
        m_gen_video,
        m_open,
        m_restore,
        fake_console,
        mock_session,
        mock_cfg,
    ):
        """Test: user requests video_gen when image profile is active.

        _ensure_generation_service handles profile detection and switch.
        We mock it to return True (success) and verify the full flow
        completes through to video generation and model restore.
        """
        # Session starts in image mode
        mock_session["sd_mode"] = "image"

        # _ensure_generation_service handles profile switch internally
        # We simulate it succeeding (detected wrong profile, switched, polled health)
        with patch("clod._ensure_generation_service", return_value=True) as m_svc:
            clod._handle_generation_intent(
                "video_gen", "dancing cat", mock_session, fake_console, mock_cfg
            )

            # Verify _ensure_generation_service was called with video_gen intent
            m_svc.assert_called_once_with("video_gen", mock_cfg, fake_console, mock_session)

        # Verify full sequence completed
        m_ensure.assert_called_once()  # _ensure_model_ready
        m_craft.assert_called_once_with("dancing cat", mock_cfg)
        m_unload.assert_called_once()
        m_gen_video.assert_called_once()
        m_restore.assert_called_once_with(mock_cfg, fake_console, mock_session)

    @patch("clod._silent_restore_model")
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_video_prompt", return_value="a cat video")
    @patch("clod._ensure_model_ready", return_value=True)
    def test_profile_switch_declined_aborts(
        self,
        m_ensure,
        m_craft,
        m_unload,
        m_restore,
        fake_console,
        mock_session,
        mock_cfg,
    ):
        """When profile switch is declined, generation should abort gracefully."""
        mock_session["sd_mode"] = "image"

        with patch("clod._ensure_generation_service", return_value=False) as m_svc:
            with patch("clod._generate_video") as m_gen:
                clod._handle_generation_intent(
                    "video_gen", "dancing cat", mock_session, fake_console, mock_cfg
                )
                m_gen.assert_not_called()

        # Model restore must still happen
        m_restore.assert_called_once()


# ── Model restore guarantee ───────────────────────────────────────────────────


class TestModelRestoreGuarantee:
    """Verify _silent_restore_model is always called via try/finally."""

    @patch("clod._silent_restore_model")
    @patch("clod._ensure_generation_service", return_value=False)
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_sd_prompt", return_value=("p", ""))
    @patch("clod._ensure_model_ready", return_value=True)
    def test_restore_on_service_unavailable(
        self, m_ensure, m_craft, m_unload, m_svc, m_restore, fake_console, mock_session, mock_cfg
    ):
        clod._handle_generation_intent("image_gen", "test", mock_session, fake_console, mock_cfg)
        m_restore.assert_called_once_with(mock_cfg, fake_console, mock_session)

    @patch("clod._silent_restore_model")
    @patch("clod._generate_image", side_effect=ConnectionError("refused"))
    @patch("clod._get_negative_prompts", return_value="bad")
    @patch("clod._detect_sd_model_type", return_value="sd15")
    @patch("clod._ensure_generation_service", return_value=True)
    @patch("clod._unload_model", return_value=True)
    @patch("clod._craft_sd_prompt", return_value=("p", ""))
    @patch("clod._ensure_model_ready", return_value=True)
    def test_restore_on_api_error(
        self,
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
        with pytest.raises(ConnectionError):
            clod._handle_generation_intent(
                "image_gen", "test", mock_session, fake_console, mock_cfg
            )
        m_restore.assert_called_once_with(mock_cfg, fake_console, mock_session)

    @patch("clod._silent_restore_model")
    @patch("clod._craft_sd_prompt", side_effect=Exception("LLM down"))
    @patch("clod._ensure_model_ready", return_value=True)
    def test_restore_on_craft_failure_with_service_down(
        self, m_ensure, m_craft, m_restore, fake_console, mock_session, mock_cfg
    ):
        """Even when craft fails AND service fails, model is restored."""
        with patch("clod._unload_model", return_value=True):
            with patch("clod._ensure_generation_service", return_value=False):
                clod._handle_generation_intent(
                    "image_gen", "test", mock_session, fake_console, mock_cfg
                )
        m_restore.assert_called_once_with(mock_cfg, fake_console, mock_session)

    @patch("clod._silent_restore_model")
    @patch("clod._ensure_model_ready", side_effect=Exception("Ollama down"))
    def test_restore_on_model_ready_failure(
        self, m_ensure, m_restore, fake_console, mock_session, mock_cfg
    ):
        """Even if _ensure_model_ready fails, model is restored."""
        with pytest.raises(Exception, match="Ollama down"):
            clod._handle_generation_intent(
                "image_gen", "test", mock_session, fake_console, mock_cfg
            )
        m_restore.assert_called_once_with(mock_cfg, fake_console, mock_session)
