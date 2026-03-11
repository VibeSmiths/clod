"""
Unit tests for _compose_base and _reset_service Docker lifecycle helpers.
"""

import pathlib
import subprocess as _sp
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest

import clod

# ── helpers ────────────────────────────────────────────────────────────────────


class _SilentConsole:
    """Console stub that suppresses output."""

    def __init__(self):
        self.printed = []

    def print(self, *args, **kwargs):
        self.printed.append(args[0] if args else "")

    def input(self, *a, **k):
        return ""


class _InputConsole(_SilentConsole):
    """Console stub with configurable input response."""

    def __init__(self, input_val="n"):
        super().__init__()
        self._input_val = input_val

    def input(self, *a, **k):
        return self._input_val


# ── _compose_base ─────────────────────────────────────────────────────────────


def test_compose_base_with_dotenv(tmp_path):
    """cfg with compose_file and dotenv_file (existing) includes --env-file."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")
    dotenv = tmp_path / ".env"
    dotenv.write_text("FOO=bar")

    cfg = {"compose_file": str(compose), "dotenv_file": str(dotenv)}
    cmd = clod._compose_base(cfg)

    assert "--env-file" in cmd
    assert str(dotenv) in cmd
    assert "-f" in cmd
    assert str(compose) in cmd


def test_compose_base_without_dotenv(tmp_path):
    """cfg with compose_file but no dotenv_file omits --env-file."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")

    cfg = {"compose_file": str(compose)}
    cmd = clod._compose_base(cfg)

    assert "--env-file" not in cmd
    assert "-f" in cmd


def test_compose_base_dotenv_missing_file(tmp_path):
    """cfg with dotenv_file but file doesn't exist: --env-file omitted."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")

    cfg = {"compose_file": str(compose), "dotenv_file": str(tmp_path / "nonexistent.env")}
    cmd = clod._compose_base(cfg)

    assert "--env-file" not in cmd


# ── _reset_service ────────────────────────────────────────────────────────────


@pytest.fixture
def reset_cfg(tmp_path):
    """Return a cfg dict with real compose and dotenv files."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")
    dotenv = tmp_path / ".env"
    dotenv.write_text("")
    return {"compose_file": str(compose), "dotenv_file": str(dotenv)}


def _make_subprocess_mock(results_by_action=None):
    """Create a subprocess.run mock returning results based on action keyword.

    results_by_action: dict mapping action keyword to CompletedProcess or exception.
    Default: all succeed (returncode=0).
    """
    if results_by_action is None:
        results_by_action = {}

    success = _sp.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    calls = []

    def mock_run(cmd, *args, **kwargs):
        calls.append(cmd)
        # Detect action from command: stop, rm, up
        for action, result in results_by_action.items():
            if action in cmd:
                if isinstance(result, Exception):
                    raise result
                return result
        return success

    return mock_run, calls


def test_reset_service_happy_path(monkeypatch, reset_cfg):
    """All subprocess calls succeed, delete_mode='none': returns True."""
    mock_run, calls = _make_subprocess_mock()
    monkeypatch.setattr(clod.subprocess, "run", mock_run)
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("."))

    con = _SilentConsole()
    result = clod._reset_service("ollama", [], reset_cfg, con, delete_mode="none")

    assert result is True
    assert any("redeployed" in str(p) for p in con.printed)
    # Should have 3 subprocess calls: stop, rm, up
    assert len(calls) == 3


def test_reset_service_stop_failure(monkeypatch, reset_cfg):
    """Stop returning nonzero: continues to rm and up (graceful degradation)."""
    fail = _sp.CompletedProcess(args=[], returncode=1, stdout="", stderr="no such service")
    mock_run, calls = _make_subprocess_mock({"stop": fail})
    monkeypatch.setattr(clod.subprocess, "run", mock_run)
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("."))

    con = _SilentConsole()
    result = clod._reset_service("ollama", [], reset_cfg, con, delete_mode="none")

    assert result is True
    assert len(calls) == 3  # stop, rm, up all attempted


def test_reset_service_stop_exception(monkeypatch, reset_cfg):
    """Stop raising TimeoutExpired: continues gracefully."""
    timeout_exc = _sp.TimeoutExpired(cmd=["docker"], timeout=30)
    mock_run, calls = _make_subprocess_mock({"stop": timeout_exc})
    monkeypatch.setattr(clod.subprocess, "run", mock_run)
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("."))

    con = _SilentConsole()
    result = clod._reset_service("ollama", [], reset_cfg, con, delete_mode="none")

    assert result is True
    # rm and up still called
    assert len(calls) >= 2


def test_reset_service_rm_failure(monkeypatch, reset_cfg):
    """rm returning nonzero: continues to up."""
    fail = _sp.CompletedProcess(args=[], returncode=1, stdout="", stderr="rm error")
    mock_run, calls = _make_subprocess_mock({"rm": fail})
    monkeypatch.setattr(clod.subprocess, "run", mock_run)
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("."))

    con = _SilentConsole()
    result = clod._reset_service("ollama", [], reset_cfg, con, delete_mode="none")

    assert result is True
    assert len(calls) == 3


def test_reset_service_up_failure(monkeypatch, reset_cfg):
    """Up returning nonzero: returns False."""
    fail = _sp.CompletedProcess(args=[], returncode=1, stdout="", stderr="up failed")
    mock_run, _ = _make_subprocess_mock({"up": fail})
    monkeypatch.setattr(clod.subprocess, "run", mock_run)

    con = _SilentConsole()
    result = clod._reset_service("ollama", [], reset_cfg, con, delete_mode="none")

    assert result is False
    assert any("up failed" in str(p) for p in con.printed)


def test_reset_service_up_file_not_found(monkeypatch, reset_cfg):
    """Up raising FileNotFoundError: returns False, prints 'docker CLI not found'."""
    mock_run, _ = _make_subprocess_mock({"up": FileNotFoundError("docker not found")})
    monkeypatch.setattr(clod.subprocess, "run", mock_run)

    con = _SilentConsole()
    result = clod._reset_service("ollama", [], reset_cfg, con, delete_mode="none")

    assert result is False
    assert any("docker CLI not found" in str(p) for p in con.printed)


def test_reset_service_delete_mode_all(monkeypatch, reset_cfg, tmp_path):
    """delete_mode='all': data dirs are deleted via shutil.rmtree."""
    mock_run, _ = _make_subprocess_mock()
    monkeypatch.setattr(clod.subprocess, "run", mock_run)
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("."))

    data_dir = tmp_path / "ollama_data"
    data_dir.mkdir()
    (data_dir / "models").mkdir()

    con = _SilentConsole()
    result = clod._reset_service("ollama", [str(data_dir)], reset_cfg, con, delete_mode="all")

    assert result is True
    assert not data_dir.exists()


def test_reset_service_delete_mode_each_yes(monkeypatch, reset_cfg, tmp_path):
    """delete_mode='each', user says yes: dir deleted."""
    mock_run, _ = _make_subprocess_mock()
    monkeypatch.setattr(clod.subprocess, "run", mock_run)
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("."))

    data_dir = tmp_path / "ollama_data"
    data_dir.mkdir()

    con = _InputConsole("y")
    result = clod._reset_service("ollama", [str(data_dir)], reset_cfg, con, delete_mode="each")

    assert result is True
    assert not data_dir.exists()


def test_reset_service_delete_mode_each_no(monkeypatch, reset_cfg, tmp_path):
    """delete_mode='each', user says no: dir preserved."""
    mock_run, _ = _make_subprocess_mock()
    monkeypatch.setattr(clod.subprocess, "run", mock_run)
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("."))

    data_dir = tmp_path / "ollama_data"
    data_dir.mkdir()

    con = _InputConsole("n")
    result = clod._reset_service("ollama", [str(data_dir)], reset_cfg, con, delete_mode="each")

    assert result is True
    assert data_dir.exists()


def test_reset_service_delete_mode_none(monkeypatch, reset_cfg, tmp_path):
    """delete_mode='none': data dirs preserved."""
    mock_run, _ = _make_subprocess_mock()
    monkeypatch.setattr(clod.subprocess, "run", mock_run)
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("."))

    data_dir = tmp_path / "ollama_data"
    data_dir.mkdir()

    con = _SilentConsole()
    result = clod._reset_service("ollama", [str(data_dir)], reset_cfg, con, delete_mode="none")

    assert result is True
    assert data_dir.exists()


def test_reset_service_restores_configs(monkeypatch, reset_cfg):
    """When service has entries in _SERVICE_CONFIGS, _ensure_local_configs is called."""
    mock_run, _ = _make_subprocess_mock()
    monkeypatch.setattr(clod.subprocess, "run", mock_run)

    ensure_calls = []

    def track_ensure(root, online_ok, console_obj, targets=None):
        ensure_calls.append({"root": root, "targets": targets})
        return {"restored": [], "failed": []}

    monkeypatch.setattr(clod, "_ensure_local_configs", track_ensure)
    monkeypatch.setattr(clod, "_get_clod_root", lambda: pathlib.Path("/fake/root"))

    con = _SilentConsole()
    # litellm is in _SERVICE_CONFIGS
    result = clod._reset_service("litellm", [], reset_cfg, con, delete_mode="none")

    assert result is True
    assert len(ensure_calls) == 1
    assert ensure_calls[0]["targets"] == ["litellm/config.yaml"]
    assert ensure_calls[0]["root"] == pathlib.Path("/fake/root")
