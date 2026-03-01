"""
Tests for sd_switch_mode, comfyui_docker_action_video,
find_comfyui_container (exception path), comfyui_docker_action (error paths),
and update_dotenv_key (exception path).
"""

import sys
import subprocess
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod


class _MockResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ── find_comfyui_container (exception path) ────────────────────────────────────


def test_find_comfyui_container_exception(monkeypatch):
    """When subprocess.run raises, find_comfyui_container returns None."""

    def raise_err(*a, **k):
        raise RuntimeError("docker socket error")

    monkeypatch.setattr(subprocess, "run", raise_err)
    result = clod.find_comfyui_container()
    assert result is None


# ── comfyui_docker_action (error paths) ───────────────────────────────────────


def test_comfyui_docker_action_nonzero_returncode(monkeypatch):
    """docker stop exits non-zero → returns (False, stderr message)."""
    monkeypatch.setattr(clod, "find_comfyui_container", lambda: "comfyui")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _MockResult(returncode=1, stderr="no such container"),
    )
    ok, msg = clod.comfyui_docker_action("stop")
    assert ok is False
    assert "no such container" in msg


def test_comfyui_docker_action_generic_exception(monkeypatch):
    """Generic exception from docker run → returns (False, str(e))."""
    monkeypatch.setattr(clod, "find_comfyui_container", lambda: "comfyui")

    def raise_generic(*a, **k):
        raise PermissionError("access denied")

    monkeypatch.setattr(subprocess, "run", raise_generic)
    ok, msg = clod.comfyui_docker_action("stop")
    assert ok is False
    assert "access denied" in msg


# ── update_dotenv_key (exception path) ────────────────────────────────────────


def test_update_dotenv_key_write_failure(monkeypatch, tmp_path):
    """When write_text fails, update_dotenv_key returns False."""
    env = tmp_path / ".env"
    env.write_text("FOO=bar\n")

    original_write = pathlib.Path.write_text

    def raise_on_write(self, *args, **kwargs):
        raise IOError("disk full")

    monkeypatch.setattr(pathlib.Path, "write_text", raise_on_write)
    result = clod.update_dotenv_key(str(env), "FOO", "new_value")
    assert result is False


# ── sd_switch_mode (docker subprocess paths) ───────────────────────────────────


def test_sd_switch_mode_success_all_docker_ok(monkeypatch, tmp_path):
    """All subprocess calls succeed → returns (True, message)."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")
    dotenv = tmp_path / ".env"
    dotenv.write_text("IMAGE_GENERATION_ENGINE=automatic1111\n")

    cfg = {"compose_file": str(compose), "dotenv_file": str(dotenv)}

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _MockResult(returncode=0),
    )
    ok, msg = clod.sd_switch_mode("video", cfg)
    assert ok is True
    assert "video" in msg


def test_sd_switch_mode_stop_fails(monkeypatch, tmp_path):
    """Stop phase fails → returns (False, error)."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")

    cfg = {"compose_file": str(compose), "dotenv_file": ""}
    call_count = [0]

    def mock_run(*a, **k):
        call_count[0] += 1
        if call_count[0] == 1:
            return _MockResult(returncode=1, stderr="cannot stop")
        return _MockResult(returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    ok, msg = clod.sd_switch_mode("video", cfg)
    assert ok is False
    assert "cannot stop" in msg or "stop" in msg.lower()


def test_sd_switch_mode_up_fails(monkeypatch, tmp_path):
    """Up phase fails → returns (False, error)."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")

    cfg = {"compose_file": str(compose), "dotenv_file": ""}
    call_count = [0]

    def mock_run(*a, **k):
        call_count[0] += 1
        if call_count[0] == 2:
            return _MockResult(returncode=1, stderr="image not found")
        return _MockResult(returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    ok, msg = clod.sd_switch_mode("video", cfg)
    assert ok is False
    assert "image not found" in msg or "up" in msg.lower()


def test_sd_switch_mode_recreate_fails(monkeypatch, tmp_path):
    """open-webui recreate phase fails → returns (False, error)."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")

    cfg = {"compose_file": str(compose), "dotenv_file": ""}
    call_count = [0]

    def mock_run(*a, **k):
        call_count[0] += 1
        if call_count[0] == 3:
            return _MockResult(returncode=1, stderr="recreate failed")
        return _MockResult(returncode=0)

    monkeypatch.setattr(subprocess, "run", mock_run)
    ok, msg = clod.sd_switch_mode("image", cfg)
    assert ok is False
    assert "recreate" in msg.lower() or "failed" in msg.lower()


def test_sd_switch_mode_exception_in_subprocess(monkeypatch, tmp_path):
    """subprocess.run raises → errors captured, returns (False, ...)."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")

    cfg = {"compose_file": str(compose), "dotenv_file": ""}

    def raise_err(*a, **k):
        raise FileNotFoundError("docker not found")

    monkeypatch.setattr(subprocess, "run", raise_err)
    ok, msg = clod.sd_switch_mode("video", cfg)
    assert ok is False


def test_sd_switch_mode_dotenv_update_fails(monkeypatch, tmp_path):
    """When update_dotenv_key returns False, an error note is added but mode still switches."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")
    dotenv = tmp_path / ".env"
    dotenv.write_text("FOO=bar\n")

    cfg = {"compose_file": str(compose), "dotenv_file": str(dotenv)}

    # Make update_dotenv_key return False to trigger error append at line 670
    monkeypatch.setattr(clod, "update_dotenv_key", lambda *a, **k: False)

    # All subprocess calls succeed
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _MockResult(returncode=0))

    ok, msg = clod.sd_switch_mode("video", cfg)
    # The .env update failure adds to errors, so ok is False
    assert ok is False
    assert "update .env" in msg


def test_sd_switch_mode_image_to_image_always_video_to_image(monkeypatch, tmp_path):
    """Switching to 'image' uses 'video' as the from_mode."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")
    dotenv = tmp_path / ".env"
    dotenv.write_text("IMAGE_GENERATION_ENGINE=comfyui\n")

    cfg = {"compose_file": str(compose), "dotenv_file": str(dotenv)}

    cmds = []

    def capture_run(cmd, **k):
        cmds.append(cmd)
        return _MockResult(returncode=0)

    monkeypatch.setattr(subprocess, "run", capture_run)
    ok, msg = clod.sd_switch_mode("image", cfg)
    assert ok is True
    # .env should now have automatic1111
    assert "automatic1111" in dotenv.read_text()


# ── comfyui_docker_action_video ────────────────────────────────────────────────


def test_comfyui_docker_action_video_no_container(monkeypatch):
    """When docker ps returns no container, returns (False, not found message)."""
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _MockResult(returncode=0, stdout="")
    )
    ok, msg = clod.comfyui_docker_action_video("stop")
    assert ok is False
    assert "not found" in msg


def test_comfyui_docker_action_video_success(monkeypatch):
    """Container found and action succeeds → (True, ...)."""
    call_count = [0]

    def mock_run(*a, **k):
        call_count[0] += 1
        if call_count[0] == 1:
            return _MockResult(returncode=0, stdout="comfyui-video\n")
        return _MockResult(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", mock_run)
    ok, msg = clod.comfyui_docker_action_video("stop")
    assert ok is True


def test_comfyui_docker_action_video_action_nonzero(monkeypatch):
    """Action exits non-zero → (False, stderr or message)."""
    call_count = [0]

    def mock_run(*a, **k):
        call_count[0] += 1
        if call_count[0] == 1:
            return _MockResult(returncode=0, stdout="comfyui-video\n")
        return _MockResult(returncode=1, stderr="stop failed")

    monkeypatch.setattr(subprocess, "run", mock_run)
    ok, msg = clod.comfyui_docker_action_video("stop")
    # returncode != 0 means the tuple is (False, stderr or fallback)
    assert ok is False


def test_comfyui_docker_action_video_docker_not_found(monkeypatch):
    """docker CLI not found during action → (False, 'docker CLI not found')."""
    call_count = [0]

    def mock_run(*a, **k):
        call_count[0] += 1
        if call_count[0] == 1:
            return _MockResult(returncode=0, stdout="comfyui-video\n")
        raise FileNotFoundError("docker not found")

    monkeypatch.setattr(subprocess, "run", mock_run)
    ok, msg = clod.comfyui_docker_action_video("stop")
    assert ok is False
    assert "docker CLI not found" in msg


def test_comfyui_docker_action_video_generic_exception(monkeypatch):
    """Generic exception during action → (False, str(e))."""
    call_count = [0]

    def mock_run(*a, **k):
        call_count[0] += 1
        if call_count[0] == 1:
            return _MockResult(returncode=0, stdout="comfyui-video\n")
        raise TimeoutError("timed out")

    monkeypatch.setattr(subprocess, "run", mock_run)
    ok, msg = clod.comfyui_docker_action_video("stop")
    assert ok is False
    assert "timed out" in msg


def test_comfyui_docker_action_video_ps_exception(monkeypatch):
    """Exception in docker ps → container is None → (False, not found)."""

    def raise_err(*a, **k):
        raise RuntimeError("socket error")

    monkeypatch.setattr(subprocess, "run", raise_err)
    ok, msg = clod.comfyui_docker_action_video("stop")
    assert ok is False
    assert "not found" in msg
