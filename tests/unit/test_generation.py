"""
Unit tests for image generation pipeline functions (Phase 4, Plan 01).
"""

import base64
import hashlib
import os
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import responses as resp_lib

import clod

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_cfg():
    return {
        "ollama_url": "http://localhost:11434",
        "sd_output_dir": "",  # will be overridden per test
        "default_model": "qwen2.5-coder:14b",
    }


@pytest.fixture
def fake_console(monkeypatch):
    """Minimal fake console for generation tests."""
    import io
    from rich.console import Console as _RC

    class _FC:
        def __init__(self):
            self._real = _RC(file=io.StringIO(), force_terminal=True, width=80)

        def __getattr__(self, name):
            return getattr(self._real, name)

        def __enter__(self):
            return self._real.__enter__()

        def __exit__(self, *args):
            return self._real.__exit__(*args)

        def print(self, *a, **kw):
            pass

        def input(self, *a, **kw):
            return ""

        def status(self, *a, **kw):
            import contextlib

            return contextlib.nullcontext()

    fc = _FC()
    monkeypatch.setattr(clod, "console", fc)
    return fc


# ---------------------------------------------------------------------------
# _parse_crafted_prompt tests
# ---------------------------------------------------------------------------


class TestParseCraftedPrompt:
    def test_basic_prompt(self):
        text = "masterpiece, best quality, sunset over mountains"
        pos, exc = clod._parse_crafted_prompt(text)
        assert pos == "masterpiece, best quality, sunset over mountains"
        assert exc == ""

    def test_with_exclude(self):
        text = "masterpiece, best quality, sunset\nEXCLUDE: clouds"
        pos, exc = clod._parse_crafted_prompt(text)
        assert pos == "masterpiece, best quality, sunset"
        assert exc == "clouds"

    def test_no_exclusions(self):
        text = "highly detailed, cat sitting on a windowsill"
        pos, exc = clod._parse_crafted_prompt(text)
        assert pos.strip() != ""
        assert exc == ""


# ---------------------------------------------------------------------------
# _craft_sd_prompt tests
# ---------------------------------------------------------------------------


class TestCraftSdPrompt:
    @resp_lib.activate
    def test_returns_optimized_prompt(self, mock_cfg):
        resp_lib.add(
            resp_lib.POST,
            "http://localhost:11434/api/chat",
            json={"message": {"content": "masterpiece, best quality, a cute cat, highly detailed"}},
            status=200,
        )
        pos, exc = clod._craft_sd_prompt("draw a cute cat", mock_cfg)
        assert "masterpiece" in pos
        assert exc == ""

    @resp_lib.activate
    def test_parses_exclude_line(self, mock_cfg):
        resp_lib.add(
            resp_lib.POST,
            "http://localhost:11434/api/chat",
            json={
                "message": {
                    "content": "masterpiece, best quality, sunset over mountains\nEXCLUDE: clouds"
                }
            },
            status=200,
        )
        pos, exc = clod._craft_sd_prompt("sunset without clouds", mock_cfg)
        assert "sunset" in pos
        assert exc == "clouds"

    @resp_lib.activate
    def test_no_exclusions(self, mock_cfg):
        resp_lib.add(
            resp_lib.POST,
            "http://localhost:11434/api/chat",
            json={"message": {"content": "masterpiece, a beautiful landscape"}},
            status=200,
        )
        pos, exc = clod._craft_sd_prompt("pretty landscape", mock_cfg)
        assert pos != ""
        assert exc == ""

    @resp_lib.activate
    def test_network_error(self, mock_cfg):
        resp_lib.add(
            resp_lib.POST,
            "http://localhost:11434/api/chat",
            body=ConnectionError("refused"),
        )
        pos, exc = clod._craft_sd_prompt("a dog", mock_cfg)
        assert pos == "a dog"  # graceful fallback
        assert exc == ""


# ---------------------------------------------------------------------------
# _detect_sd_model_type tests
# ---------------------------------------------------------------------------


class TestDetectSdModelType:
    @resp_lib.activate
    def test_sdxl(self):
        resp_lib.add(
            resp_lib.GET,
            "http://localhost:7860/sdapi/v1/options",
            json={"sd_model_checkpoint": "realvisxlV30_sdxl.safetensors"},
            status=200,
        )
        assert clod._detect_sd_model_type() == "sdxl"

    @resp_lib.activate
    def test_xl_keyword(self):
        resp_lib.add(
            resp_lib.GET,
            "http://localhost:7860/sdapi/v1/options",
            json={"sd_model_checkpoint": "somemodel_xl_v2.safetensors"},
            status=200,
        )
        assert clod._detect_sd_model_type() == "sdxl"

    @resp_lib.activate
    def test_pony(self):
        resp_lib.add(
            resp_lib.GET,
            "http://localhost:7860/sdapi/v1/options",
            json={"sd_model_checkpoint": "ponyDiffusionV6.safetensors"},
            status=200,
        )
        assert clod._detect_sd_model_type() == "sdxl"

    @resp_lib.activate
    def test_sd15(self):
        resp_lib.add(
            resp_lib.GET,
            "http://localhost:7860/sdapi/v1/options",
            json={"sd_model_checkpoint": "v1-5-pruned-emaonly.safetensors"},
            status=200,
        )
        assert clod._detect_sd_model_type() == "sd15"

    @resp_lib.activate
    def test_unreachable(self):
        resp_lib.add(
            resp_lib.GET,
            "http://localhost:7860/sdapi/v1/options",
            body=ConnectionError("refused"),
        )
        assert clod._detect_sd_model_type() == "sd15"


# ---------------------------------------------------------------------------
# _get_negative_prompts tests
# ---------------------------------------------------------------------------


class TestGetNegativePrompts:
    def test_sd15(self):
        neg = clod._get_negative_prompts("sd15")
        assert "extra limbs" in neg
        assert "mutated hands" in neg

    def test_sdxl(self):
        neg = clod._get_negative_prompts("sdxl")
        assert "low quality" in neg
        # SDXL negatives should be shorter
        assert "extra limbs" not in neg

    def test_with_user_exclusions(self):
        neg = clod._get_negative_prompts("sd15", "clouds, rain")
        assert "clouds, rain" in neg
        assert "extra limbs" in neg


# ---------------------------------------------------------------------------
# _generate_image tests
# ---------------------------------------------------------------------------


class TestGenerateImage:
    @resp_lib.activate
    def test_success(self, mock_cfg, fake_console, tmp_path):
        mock_cfg["sd_output_dir"] = str(tmp_path)

        # Create a fake 1x1 PNG as base64
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        b64_img = base64.b64encode(fake_png).decode()

        resp_lib.add(
            resp_lib.POST,
            "http://localhost:7860/sdapi/v1/txt2img",
            json={"images": [b64_img]},
            status=200,
        )
        # Progress polling endpoint
        resp_lib.add(
            resp_lib.GET,
            "http://localhost:7860/sdapi/v1/progress",
            json={"progress": 0.5, "eta_relative": 5.0},
            status=200,
        )

        params = {
            "steps": 25,
            "cfg_scale": 7,
            "width": 512,
            "height": 512,
            "sampler_name": "DPM++ 2M",
        }
        result = clod._generate_image("a cat", "low quality", params, mock_cfg, fake_console)

        assert result is not None
        assert os.path.isfile(result)
        assert "clod_" in os.path.basename(result)
        assert result.endswith(".png")

    @resp_lib.activate
    def test_api_error(self, mock_cfg, fake_console, tmp_path):
        mock_cfg["sd_output_dir"] = str(tmp_path)

        resp_lib.add(
            resp_lib.POST,
            "http://localhost:7860/sdapi/v1/txt2img",
            json={"error": "internal"},
            status=500,
        )
        resp_lib.add(
            resp_lib.GET,
            "http://localhost:7860/sdapi/v1/progress",
            json={"progress": 0.0},
            status=200,
        )

        params = {
            "steps": 25,
            "cfg_scale": 7,
            "width": 512,
            "height": 512,
            "sampler_name": "DPM++ 2M",
        }
        result = clod._generate_image("a cat", "low quality", params, mock_cfg, fake_console)
        assert result is None

    @resp_lib.activate
    def test_no_images(self, mock_cfg, fake_console, tmp_path):
        mock_cfg["sd_output_dir"] = str(tmp_path)

        resp_lib.add(
            resp_lib.POST,
            "http://localhost:7860/sdapi/v1/txt2img",
            json={"images": []},
            status=200,
        )
        resp_lib.add(
            resp_lib.GET,
            "http://localhost:7860/sdapi/v1/progress",
            json={"progress": 0.0},
            status=200,
        )

        params = {
            "steps": 25,
            "cfg_scale": 7,
            "width": 512,
            "height": 512,
            "sampler_name": "DPM++ 2M",
        }
        result = clod._generate_image("a cat", "low quality", params, mock_cfg, fake_console)
        assert result is None


# ---------------------------------------------------------------------------
# _save_generation_output tests
# ---------------------------------------------------------------------------


class TestSaveGenerationOutput:
    def test_naming_pattern(self, tmp_path):
        data = b"fake image data for testing"
        result = clod._save_generation_output(data, "png", str(tmp_path))
        assert os.path.isfile(result)
        name = os.path.basename(result)
        assert name.startswith("clod_")
        assert name.endswith(".png")
        # Pattern: clod_YYYYMMDD_HHMMSS_XXXX.png
        parts = name.replace(".png", "").split("_")
        assert len(parts) == 4  # clod, date, time, hash

    def test_creates_dir(self, tmp_path):
        new_dir = os.path.join(str(tmp_path), "nested", "output")
        data = b"test data"
        result = clod._save_generation_output(data, "png", new_dir)
        assert os.path.isfile(result)
        assert os.path.isdir(new_dir)
