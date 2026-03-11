"""
Unit tests for /services slash command routing via handle_slash().

Covers: status, start, stop, reset sub-commands.
"""

import pathlib
import subprocess as _sp
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import responses as resp_lib

import clod
from clod import handle_slash

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


@pytest.fixture
def service_cfg(mock_cfg, tmp_path):
    """Extend mock_cfg with compose_file and dotenv_file pointing to tmp_path."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'\nservices:\n  ollama:\n    image: ollama\n")
    dotenv = tmp_path / ".env"
    dotenv.write_text("OLLAMA_DATA_DIR=/data/ollama\n")
    mock_cfg["compose_file"] = str(compose)
    mock_cfg["dotenv_file"] = str(dotenv)
    return mock_cfg


@pytest.fixture
def service_state(service_cfg, mock_session_state):
    """Session state with service cfg, health, and features."""
    mock_session_state["cfg"] = service_cfg
    mock_session_state["health"] = {
        "ollama": True,
        "litellm": True,
        "pipelines": True,
        "searxng": True,
        "chroma": True,
    }
    mock_session_state["features"] = clod._compute_features({}, mock_session_state["health"])
    return mock_session_state


def _register_all_health(status=200):
    """Register all 5 health check endpoints with given status."""
    resp_lib.add(
        resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []}, status=status
    )
    resp_lib.add(resp_lib.GET, "http://localhost:4000/health", json={"status": "ok"}, status=status)
    resp_lib.add(resp_lib.GET, "http://localhost:9099/", json={}, status=status)
    resp_lib.add(resp_lib.GET, "http://localhost:8080/healthz", body="OK", status=status)
    resp_lib.add(resp_lib.GET, "http://localhost:8000/api/v2/heartbeat", json={}, status=status)


# ── /services status ──────────────────────────────────────────────────────────


@resp_lib.activate
def test_services_status_all_healthy(monkeypatch, service_state):
    """Status sub-command shows health for all 5 services, updates session_state."""
    monkeypatch.setattr(clod, "console", _SilentConsole())
    _register_all_health(200)

    result = handle_slash("/services", service_state, [])

    assert result is True
    health = service_state["health"]
    assert health["ollama"] is True
    assert health["litellm"] is True
    assert health["pipelines"] is True
    assert health["searxng"] is True
    assert health["chroma"] is True


@resp_lib.activate
def test_services_status_some_down(monkeypatch, service_state):
    """Status reflects mixed state when some services are down."""
    monkeypatch.setattr(clod, "console", _SilentConsole())
    # Only register ollama; others will raise ConnectionError
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []}, status=200)

    result = handle_slash("/services", service_state, [])

    assert result is True
    health = service_state["health"]
    assert health["ollama"] is True
    assert health["litellm"] is False
    assert health["pipelines"] is False
    assert health["searxng"] is False
    assert health["chroma"] is False


# ── /services start ───────────────────────────────────────────────────────────


@resp_lib.activate
def test_services_start_all_running(monkeypatch, service_state):
    """When all services are healthy, prints 'All core services' without docker compose."""
    con = _SilentConsole()
    monkeypatch.setattr(clod, "console", con)
    _register_all_health(200)

    result = handle_slash("/services start", service_state, [])

    assert result is True
    assert any("All core services" in str(p) for p in con.printed)


@resp_lib.activate
def test_services_start_missing_services(monkeypatch, service_state):
    """When some are down and user accepts, features/health updated."""
    con = _SilentConsole()
    monkeypatch.setattr(clod, "console", con)
    # First health check: only ollama up
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []}, status=200)
    # After docker startup, second health check: all up
    _register_all_health(200)

    monkeypatch.setattr(clod, "_offer_docker_startup", lambda cfg, missing, con_obj: True)

    result = handle_slash("/services start", service_state, [])

    assert result is True
    assert "features" in service_state
    assert "health" in service_state


@resp_lib.activate
def test_services_start_docker_declined(monkeypatch, service_state):
    """When user declines docker startup, session_state not updated with new features."""
    con = _SilentConsole()
    monkeypatch.setattr(clod, "console", con)
    # Only ollama up
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []}, status=200)

    monkeypatch.setattr(clod, "_offer_docker_startup", lambda cfg, missing, con_obj: False)

    old_features = service_state["features"].copy()
    result = handle_slash("/services start", service_state, [])

    assert result is True
    # Features should not have been updated (no "Feature flags updated" path)
    assert service_state["features"] == old_features


# ── /services stop ────────────────────────────────────────────────────────────


def test_services_stop_confirmed(monkeypatch, service_state):
    """Stop confirmed: runs docker compose down, sets offline=True, health all False."""
    con = _InputConsole("y")
    monkeypatch.setattr(clod, "console", con)

    fake_result = _sp.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    monkeypatch.setattr(clod.subprocess, "run", lambda *a, **k: fake_result)

    result = handle_slash("/services stop", service_state, [])

    assert result is True
    assert service_state["offline"] is True
    assert all(v is False for v in service_state["health"].values())


def test_services_stop_cancelled(monkeypatch, service_state):
    """Stop cancelled: no subprocess calls, state unchanged."""
    con = _InputConsole("n")
    monkeypatch.setattr(clod, "console", con)

    subprocess_called = []
    monkeypatch.setattr(clod.subprocess, "run", lambda *a, **k: subprocess_called.append(1))

    result = handle_slash("/services stop", service_state, [])

    assert result is True
    assert subprocess_called == []


def test_services_stop_compose_failure(monkeypatch, service_state):
    """Stop with compose failure: error message printed."""
    con = _InputConsole("y")
    monkeypatch.setattr(clod, "console", con)

    fake_result = _sp.CompletedProcess(args=[], returncode=1, stdout="", stderr="permission denied")
    monkeypatch.setattr(clod.subprocess, "run", lambda *a, **k: fake_result)

    result = handle_slash("/services stop", service_state, [])

    assert result is True
    assert any("failed" in str(p) or "permission denied" in str(p) for p in con.printed)


# ── /services reset ───────────────────────────────────────────────────────────


@resp_lib.activate
def test_services_reset_single_named(monkeypatch, service_state):
    """Reset single named service: _reset_service called for ollama only."""
    con = _SilentConsole()
    monkeypatch.setattr(clod, "console", con)
    _register_all_health(200)

    reset_calls = []

    def fake_reset(service, paths, cfg, console_obj, delete_mode):
        reset_calls.append(service)
        return True

    monkeypatch.setattr(clod, "_reset_service", fake_reset)
    monkeypatch.setattr(
        clod,
        "_get_service_volumes",
        lambda cfg: {s: [] for s in clod._SERVICE_ENV_VOLUMES},
    )

    result = handle_slash("/services reset ollama", service_state, [])

    assert result is True
    assert reset_calls == ["ollama"]


@resp_lib.activate
def test_services_reset_all(monkeypatch, service_state):
    """Reset all: iterates services in dependency order."""
    con = _InputConsole("each")
    monkeypatch.setattr(clod, "console", con)
    _register_all_health(200)

    reset_calls = []

    def fake_reset(service, paths, cfg, console_obj, delete_mode):
        reset_calls.append(service)
        return True

    monkeypatch.setattr(clod, "_reset_service", fake_reset)
    monkeypatch.setattr(
        clod,
        "_get_service_volumes",
        lambda cfg: {s: [] for s in clod._SERVICE_ENV_VOLUMES},
    )

    result = handle_slash("/services reset all", service_state, [])

    assert result is True
    assert len(reset_calls) == len(clod._SERVICE_ENV_VOLUMES)
    # Verify dependency order (chroma first, open-webui last)
    assert reset_calls[0] == "chroma"
    assert reset_calls[-1] == "open-webui"


@resp_lib.activate
def test_services_reset_unknown_service(monkeypatch, service_state):
    """Reset unknown service: 'Unknown service' warning printed."""
    con = _SilentConsole()
    monkeypatch.setattr(clod, "console", con)
    _register_all_health(200)

    monkeypatch.setattr(
        clod,
        "_get_service_volumes",
        lambda cfg: {s: [] for s in clod._SERVICE_ENV_VOLUMES},
    )

    result = handle_slash("/services reset nonexistent", service_state, [])

    assert result is True
    assert any("Unknown service" in str(p) for p in con.printed)


def test_services_reset_no_compose_file(monkeypatch, service_state):
    """Reset with missing compose file: 'not found' error."""
    con = _SilentConsole()
    monkeypatch.setattr(clod, "console", con)

    service_state["cfg"]["compose_file"] = "/nonexistent/docker-compose.yml"

    result = handle_slash("/services reset ollama", service_state, [])

    assert result is True
    assert any("not found" in str(p) for p in con.printed)


@resp_lib.activate
def test_services_reset_all_with_force_yes(monkeypatch, service_state):
    """Reset all --yes: delete_mode set to 'all'."""
    con = _SilentConsole()
    monkeypatch.setattr(clod, "console", con)
    _register_all_health(200)

    reset_calls = []

    def fake_reset(service, paths, cfg, console_obj, delete_mode):
        reset_calls.append((service, delete_mode))
        return True

    monkeypatch.setattr(clod, "_reset_service", fake_reset)
    monkeypatch.setattr(
        clod,
        "_get_service_volumes",
        lambda cfg: {s: [] for s in clod._SERVICE_ENV_VOLUMES},
    )

    result = handle_slash("/services reset all --yes", service_state, [])

    assert result is True
    assert all(dm == "all" for _, dm in reset_calls)
