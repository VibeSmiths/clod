"""
Tests for MCP server functions and print_startup_banner.
"""

import sys
import types
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod

# ── _prompt_mcp_access ────────────────────────────────────────────────────────


def test_prompt_mcp_access_declines_n(monkeypatch, fake_console):
    """Entering 'n' returns (False, default_dir) without asking for a directory."""
    monkeypatch.setattr(fake_console, "input", lambda *a, **k: "n")
    ok, dir_ = clod._prompt_mcp_access({})
    assert ok is False
    assert pathlib.Path(dir_).exists()


def test_prompt_mcp_access_declines_empty(monkeypatch, fake_console):
    """Empty answer (default) returns (False, default_dir)."""
    monkeypatch.setattr(fake_console, "input", lambda *a, **k: "")
    ok, dir_ = clod._prompt_mcp_access({})
    assert ok is False


def test_prompt_mcp_access_yes_default_dir(monkeypatch, fake_console):
    """'y' then empty dir string uses the current working directory."""
    answers = iter(["y", ""])
    monkeypatch.setattr(fake_console, "input", lambda *a, **k: next(answers))
    ok, dir_ = clod._prompt_mcp_access({})
    assert ok is True
    assert pathlib.Path(dir_).is_dir()


def test_prompt_mcp_access_yes_custom_valid_dir(monkeypatch, fake_console, tmp_path):
    """'y' then a valid directory path uses that directory."""
    answers = iter(["y", str(tmp_path)])
    monkeypatch.setattr(fake_console, "input", lambda *a, **k: next(answers))
    ok, dir_ = clod._prompt_mcp_access({})
    assert ok is True
    assert dir_ == str(tmp_path.resolve())


def test_prompt_mcp_access_yes_invalid_dir(monkeypatch, fake_console):
    """'y' then a nonexistent path returns (False, default_dir) and prints error."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    answers = iter(["y", "/nonexistent_xyz_abc/path"])
    monkeypatch.setattr(fake_console, "input", lambda *a, **k: next(answers))
    ok, dir_ = clod._prompt_mcp_access({})
    assert ok is False
    assert any("Not a directory" in s for s in printed)


def test_prompt_mcp_access_eof_on_first_input(monkeypatch, fake_console):
    """EOFError on the first console.input returns (False, default_dir)."""

    def raise_eof(*a, **k):
        raise EOFError

    monkeypatch.setattr(fake_console, "input", raise_eof)
    ok, dir_ = clod._prompt_mcp_access({})
    assert ok is False


def test_prompt_mcp_access_keyboard_interrupt_on_first(monkeypatch, fake_console):
    """KeyboardInterrupt on the first console.input returns (False, default_dir)."""

    def raise_ki(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(fake_console, "input", raise_ki)
    ok, dir_ = clod._prompt_mcp_access({})
    assert ok is False


def test_prompt_mcp_access_eof_on_second_input(monkeypatch, fake_console):
    """EOFError on the directory prompt (second input) returns (False, default_dir)."""
    call_count = [0]

    def mock_input(*a, **k):
        call_count[0] += 1
        if call_count[0] == 1:
            return "y"
        raise EOFError

    monkeypatch.setattr(fake_console, "input", mock_input)
    ok, dir_ = clod._prompt_mcp_access({})
    assert ok is False


# ── start_mcp_server ──────────────────────────────────────────────────────────


def test_start_mcp_server_success(monkeypatch, fake_console, tmp_path):
    """start_mcp_server returns an httpd object on success."""
    import mcp_server as _real_mcp

    class _FakeHttpd:
        pass

    monkeypatch.setattr(_real_mcp, "start", lambda port, directory: _FakeHttpd())
    result = clod.start_mcp_server(str(tmp_path), 8765)
    assert result is not None


def test_start_mcp_server_failure(monkeypatch, fake_console, tmp_path):
    """start_mcp_server returns None and prints error when start() raises."""
    import mcp_server as _real_mcp

    def raise_err(port, directory):
        raise RuntimeError("port already in use")

    monkeypatch.setattr(_real_mcp, "start", raise_err)
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    result = clod.start_mcp_server(str(tmp_path), 8765)
    assert result is None
    assert any("failed" in s.lower() for s in printed)


# ── print_startup_banner ──────────────────────────────────────────────────────


def test_startup_banner_no_gpu_no_sys(monkeypatch, fake_console):
    """Banner renders without GPU or sys_info (CPU-only, no psutil)."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    # Should complete without error
    clod.print_startup_banner("qwen2.5-coder:14b")


def test_startup_banner_with_sys_info(monkeypatch, fake_console):
    """Banner includes CPU and RAM when sys_info is available."""
    monkeypatch.setattr(
        clod,
        "query_system_info",
        lambda: {
            "cpu_name": "Intel i9-13900K",
            "cpu_physical": 8,
            "cpu_logical": 24,
            "ram_total_mb": 65536,
            "ram_available_mb": 32768,
        },
    )
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    clod.print_startup_banner("qwen2.5-coder:14b")


def test_startup_banner_with_gpu_matching_model(monkeypatch, fake_console):
    """Banner shows GPU info and matching recommendation marker."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070 Ti SUPER", "total_mb": 16376, "free_mb": 10000},
    )
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    clod.print_startup_banner("qwen2.5-coder:14b")


def test_startup_banner_with_gpu_different_model(monkeypatch, fake_console):
    """Banner shows 'switch' hint when current model differs from recommendation."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070 Ti SUPER", "total_mb": 16376, "free_mb": 10000},
    )
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    clod.print_startup_banner("llama3.1:8b")  # not the recommended model


def test_startup_banner_with_mcp_enabled(monkeypatch, fake_console):
    """Banner shows MCP line when mcp_dir and mcp_port are provided."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    clod.print_startup_banner("model", mcp_dir="/tmp/testdir", mcp_port=8765)


def test_startup_banner_a1111_active(monkeypatch, fake_console):
    """Banner shows A1111 active tag when image SD is running."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070", "total_mb": 16384, "free_mb": 4000},
    )
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: True)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    clod.print_startup_banner("qwen2.5-coder:14b")


def test_startup_banner_comfyui_active(monkeypatch, fake_console):
    """Banner shows ComfyUI active tag when video SD is running."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070", "total_mb": 16384, "free_mb": 4000},
    )
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: True)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    clod.print_startup_banner("qwen2.5-coder:14b")


def test_startup_banner_vram_too_low_no_rec(monkeypatch, fake_console):
    """Banner handles case where VRAM is too low for any model."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 3050", "total_mb": 4096, "free_mb": 2000},
    )
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: None)
    clod.print_startup_banner("model")


def test_startup_banner_vram_too_low_with_sd_active(monkeypatch, fake_console):
    """Banner shows /sd stop hint when VRAM is too low and SD is active."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 3050", "total_mb": 4096, "free_mb": 1000},
    )
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: True)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: None)
    clod.print_startup_banner("model")


def test_startup_banner_no_gpu_high_ram(monkeypatch, fake_console):
    """Banner mentions CPU offloading when RAM >= 32 GB and no GPU."""
    monkeypatch.setattr(
        clod,
        "query_system_info",
        lambda: {
            "cpu_name": "Intel i9",
            "cpu_physical": 8,
            "cpu_logical": 16,
            "ram_total_mb": 65536,
            "ram_available_mb": 32000,
        },
    )
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    clod.print_startup_banner("model")


def test_startup_banner_sd_active_high_vram_usage(monkeypatch, fake_console):
    """Banner shows /sd hint when SD is active and using > 1 GB VRAM."""
    monkeypatch.setattr(clod, "query_system_info", lambda: {})
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070", "total_mb": 16384, "free_mb": 3000},
    )
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: True)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    clod.print_startup_banner("qwen2.5-coder:14b")
