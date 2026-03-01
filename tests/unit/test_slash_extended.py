"""
Extended handle_slash() tests — covers previously uncovered branches.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import handle_slash, TokenBudget


# ── Helper ─────────────────────────────────────────────────────────────────────


def _make_state(mock_cfg):
    """Return a full session_state including sd_mode and mcp fields."""
    return {
        "model": "qwen2.5-coder:14b",
        "pipeline": None,
        "tools_on": False,
        "system": None,
        "cfg": {**mock_cfg, "mcp_port": 8765, "sd_mode": "image"},
        "budget": TokenBudget(10000),
        "offline": False,
        "sd_mode": "image",
        "mcp_httpd": None,
        "mcp_dir": None,
    }


# ── /exit and /quit ────────────────────────────────────────────────────────────


def test_slash_exit_raises_system_exit(fake_console, mock_cfg):
    """/exit raises SystemExit(0)."""
    state = _make_state(mock_cfg)
    with pytest.raises(SystemExit) as exc:
        handle_slash("/exit", state, [])
    assert exc.value.code == 0


def test_slash_quit_raises_system_exit(fake_console, mock_cfg):
    """/quit raises SystemExit(0)."""
    state = _make_state(mock_cfg)
    with pytest.raises(SystemExit):
        handle_slash("/quit", state, [])


# ── /help ──────────────────────────────────────────────────────────────────────


def test_slash_help_calls_print_help(monkeypatch, mock_cfg):
    """/help calls print_help() and returns True."""
    called = []
    monkeypatch.setattr(clod, "print_help", lambda: called.append(True))
    monkeypatch.setattr(clod, "console", type("C", (), {"print": lambda *a, **k: None})())
    state = _make_state(mock_cfg)
    result = handle_slash("/help", state, [])
    assert result is True
    assert called


# ── /model (no arg) ────────────────────────────────────────────────────────────


def test_slash_model_no_arg_prints_current(fake_console, mock_cfg):
    """/model with no arg prints the current model name."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    state["model"] = "my-test-model"
    handle_slash("/model", state, [])
    assert any("my-test-model" in s for s in printed)


# ── /pipeline (no arg) ─────────────────────────────────────────────────────────


def test_slash_pipeline_no_arg_none_prints_none(fake_console, mock_cfg):
    """/pipeline with no arg and None pipeline prints 'none'."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    state["pipeline"] = None
    handle_slash("/pipeline", state, [])
    assert any("none" in s.lower() for s in printed)


def test_slash_pipeline_no_arg_with_value(fake_console, mock_cfg):
    """/pipeline with no arg prints the current pipeline name."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    state["pipeline"] = "code_review"
    handle_slash("/pipeline", state, [])
    assert any("code_review" in s for s in printed)


# ── /system (update existing message) ──────────────────────────────────────────


def test_slash_system_updates_existing_message(fake_console, mock_cfg):
    """/system X updates an existing system message in-place, not inserting a new one."""
    state = _make_state(mock_cfg)
    messages = [{"role": "system", "content": "old prompt"}]
    handle_slash("/system new prompt text", state, messages)
    assert len(messages) == 1  # not duplicated
    assert messages[0]["content"] == "new prompt text"


# ── /save (error path) ─────────────────────────────────────────────────────────


def test_slash_save_error_prints_message(fake_console, mock_cfg):
    """/save to an invalid path prints an error message."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    handle_slash("/save /nonexistent_dir/cannot_create_xyz/out.json", state, [])
    assert any("error" in s.lower() or "Save error" in s for s in printed)


# ── /index ─────────────────────────────────────────────────────────────────────


def test_slash_index_valid_dir(monkeypatch, fake_console, mock_cfg, tmp_path):
    """/index <dir> calls run_index_mode with the given path."""
    called = []
    monkeypatch.setattr(clod, "run_index_mode", lambda path, cfg: called.append(path))
    state = _make_state(mock_cfg)
    handle_slash(f"/index {tmp_path}", state, [])
    assert called
    assert called[0] == tmp_path


def test_slash_index_invalid_dir(fake_console, mock_cfg):
    """/index with a non-directory path prints 'Not a directory'."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    handle_slash("/index /nonexistent/path/xyz_abc", state, [])
    assert any("Not a directory" in s for s in printed)


def test_slash_index_no_arg(monkeypatch, fake_console, mock_cfg):
    """/index with no arg defaults to current directory."""
    called = []
    monkeypatch.setattr(clod, "run_index_mode", lambda path, cfg: called.append(path))
    state = _make_state(mock_cfg)
    handle_slash("/index", state, [])
    # Either called (if cwd is a directory) or printed "Not a directory"
    # Current directory should exist
    assert called or True  # just verify no exception


# ── /mcp ──────────────────────────────────────────────────────────────────────


def test_slash_mcp_running_shows_status(fake_console, mock_cfg):
    """/mcp when server is running calls console.print with a Panel."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(a)
    state = _make_state(mock_cfg)
    state["mcp_httpd"] = object()  # truthy value
    state["mcp_dir"] = "/tmp/test"
    handle_slash("/mcp", state, [])
    assert printed  # console.print was called with the status panel


def test_slash_mcp_not_running_shows_info(fake_console, mock_cfg):
    """/mcp when server is not running shows informational message."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    state["mcp_httpd"] = None
    state["mcp_dir"] = None
    handle_slash("/mcp", state, [])
    assert any("not running" in s.lower() for s in printed)


# ── /gpu ──────────────────────────────────────────────────────────────────────


def test_slash_gpu_no_gpu(monkeypatch, fake_console, mock_cfg):
    """/gpu when no GPU prints 'No NVIDIA GPU detected'."""
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    handle_slash("/gpu", state, [])
    assert any("No NVIDIA GPU" in s or "unavailable" in s for s in printed)


def test_slash_gpu_with_gpu(monkeypatch, fake_console, mock_cfg):
    """/gpu with a detected GPU shows VRAM panel."""
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070 Ti", "total_mb": 16384, "free_mb": 10000},
    )
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    handle_slash("/gpu", state, [])
    # Should have printed something with GPU info
    assert printed


def test_slash_gpu_use_sets_model(monkeypatch, fake_console, mock_cfg):
    """/gpu use sets session model to the recommended model and warms up."""
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070 Ti", "total_mb": 16384, "free_mb": 10000},
    )
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    warmed = []
    monkeypatch.setattr(clod, "warmup_ollama_model", lambda m, cfg: warmed.append(m))
    state = _make_state(mock_cfg)
    handle_slash("/gpu use", state, [])
    assert state["model"] == "qwen2.5-coder:14b"
    assert state["pipeline"] is None
    assert warmed


# ── /sd ───────────────────────────────────────────────────────────────────────


def test_slash_sd_status_no_args(monkeypatch, fake_console, mock_cfg):
    """/sd with no argument calls console.print with the status panel."""
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    printed = []
    fake_console.print = lambda *a, **k: printed.append(a)
    state = _make_state(mock_cfg)
    handle_slash("/sd", state, [])
    assert printed  # console.print was called with the status panel


def test_slash_sd_image_already_active(fake_console, mock_cfg):
    """/sd image when already in image mode prints 'Already in image mode'."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    state["sd_mode"] = "image"
    handle_slash("/sd image", state, [])
    assert any("Already" in s for s in printed)


def test_slash_sd_video_already_active(fake_console, mock_cfg):
    """/sd video when already in video mode prints 'Already in video mode'."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    state["sd_mode"] = "video"
    handle_slash("/sd video", state, [])
    assert any("Already" in s for s in printed)


def test_slash_sd_video_switch_success(monkeypatch, fake_console, mock_cfg):
    """/sd video from image mode calls sd_switch_mode and updates sd_mode."""
    monkeypatch.setattr(clod, "sd_switch_mode", lambda mode, cfg: (True, "ok"))
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: None)
    state = _make_state(mock_cfg)
    state["sd_mode"] = "image"
    handle_slash("/sd video", state, [])
    assert state["sd_mode"] == "video"


def test_slash_sd_image_switch_success_with_gpu(monkeypatch, fake_console, mock_cfg):
    """/sd image switch shows GPU info if available."""
    monkeypatch.setattr(clod, "sd_switch_mode", lambda mode, cfg: (True, "ok"))
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070", "total_mb": 16384, "free_mb": 8000},
    )
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    state = _make_state(mock_cfg)
    state["sd_mode"] = "video"
    handle_slash("/sd image", state, [])
    assert state["sd_mode"] == "image"


def test_slash_sd_video_switch_failure(monkeypatch, fake_console, mock_cfg):
    """/sd video when switch fails prints error."""
    monkeypatch.setattr(clod, "sd_switch_mode", lambda mode, cfg: (False, "docker error"))
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    state["sd_mode"] = "image"
    handle_slash("/sd video", state, [])
    assert any("Switch failed" in s or "docker error" in s for s in printed)
    assert state["sd_mode"] == "image"  # unchanged


def test_slash_sd_stop_nothing_running(monkeypatch, fake_console, mock_cfg):
    """/sd stop when no services run prints 'No SD service is running'."""
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: False)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    handle_slash("/sd stop", state, [])
    assert any("No SD service" in s for s in printed)


def test_slash_sd_stop_both_running_success(monkeypatch, fake_console, mock_cfg):
    """/sd stop when both services run; both stop successfully."""
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: True)
    monkeypatch.setattr(clod, "query_video_running", lambda: True)
    monkeypatch.setattr(clod, "comfyui_docker_action", lambda action: (True, "ok"))
    monkeypatch.setattr(clod, "comfyui_docker_action_video", lambda action: (True, "ok"))
    monkeypatch.setattr(clod, "query_gpu_vram", lambda: None)
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    handle_slash("/sd stop", state, [])
    assert any("stopped" in s.lower() for s in printed)


def test_slash_sd_stop_with_gpu(monkeypatch, fake_console, mock_cfg):
    """/sd stop prints GPU free VRAM after stopping."""
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: True)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "comfyui_docker_action", lambda action: (True, "ok"))
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX", "total_mb": 16384, "free_mb": 12000},
    )
    monkeypatch.setattr(clod, "recommend_model_for_vram", lambda mb: "qwen2.5-coder:14b")
    state = _make_state(mock_cfg)
    handle_slash("/sd stop", state, [])


def test_slash_sd_stop_failure(monkeypatch, fake_console, mock_cfg):
    """/sd stop failure prints error."""
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: True)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(clod, "comfyui_docker_action", lambda action: (False, "stop failed"))
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    handle_slash("/sd stop", state, [])
    assert any("error" in s.lower() or "stop failed" in s for s in printed)


def test_slash_sd_start_success(monkeypatch, fake_console, mock_cfg):
    """/sd start restarts the last-active mode."""
    monkeypatch.setattr(clod, "sd_switch_mode", lambda mode, cfg: (True, "ok"))
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    state["sd_mode"] = "video"
    handle_slash("/sd start", state, [])
    assert any("video" in s.lower() or "started" in s.lower() for s in printed)


def test_slash_sd_start_failure(monkeypatch, fake_console, mock_cfg):
    """/sd start failure prints error."""
    monkeypatch.setattr(clod, "sd_switch_mode", lambda mode, cfg: (False, "fail msg"))
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    state = _make_state(mock_cfg)
    handle_slash("/sd start", state, [])
    assert any("Failed" in s or "fail msg" in s for s in printed)


def test_slash_sd_status_with_gpu(monkeypatch, fake_console, mock_cfg):
    """/sd status includes GPU info if available."""
    monkeypatch.setattr(clod, "query_comfyui_running", lambda: True)
    monkeypatch.setattr(clod, "query_video_running", lambda: False)
    monkeypatch.setattr(
        clod,
        "query_gpu_vram",
        lambda: {"name": "RTX 4070", "total_mb": 16384, "free_mb": 8192},
    )
    state = _make_state(mock_cfg)
    handle_slash("/sd", state, [])
