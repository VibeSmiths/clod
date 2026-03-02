"""
Unit tests for startup helpers: _parse_dotenv, _check_service_health,
_compute_features, _setup_env_wizard, _get_service_volumes,
_get_clod_root, _ensure_local_configs.
"""

import pathlib
import shutil
import sys
import tempfile

import pytest
import responses as resp_lib

import clod

# ── _parse_dotenv ──────────────────────────────────────────────────────────────


def test_parse_dotenv_basic(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
    result = clod._parse_dotenv(str(env))
    assert result == {"FOO": "bar", "BAZ": "qux"}


def test_parse_dotenv_skips_comments(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nKEY=val\n\n# another\n", encoding="utf-8")
    result = clod._parse_dotenv(str(env))
    assert result == {"KEY": "val"}


def test_parse_dotenv_strips_quotes(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=\"hello\"\nB='world'\n", encoding="utf-8")
    result = clod._parse_dotenv(str(env))
    assert result == {"A": "hello", "B": "world"}


def test_parse_dotenv_missing_file(tmp_path):
    result = clod._parse_dotenv(str(tmp_path / "does_not_exist.env"))
    assert result == {}


def test_parse_dotenv_equals_in_value(tmp_path):
    env = tmp_path / ".env"
    env.write_text("TOKEN=abc=def=ghi\n", encoding="utf-8")
    result = clod._parse_dotenv(str(env))
    assert result == {"TOKEN": "abc=def=ghi"}


# ── _compute_features ──────────────────────────────────────────────────────────


def _all_up():
    return {"ollama": True, "litellm": True, "pipelines": True, "searxng": True, "chroma": True}


def _all_down():
    return {
        "ollama": False,
        "litellm": False,
        "pipelines": False,
        "searxng": False,
        "chroma": False,
    }


_ENV_WITH_KEY = {"ANTHROPIC_API_KEY": "sk-ant-test"}


def test_compute_features_all_healthy():
    feats = clod._compute_features(_ENV_WITH_KEY, _all_up())
    assert feats["cloud_models"] is True
    assert feats["web_search"] is True
    assert feats["semantic_recall"] is True
    assert feats["pipelines"] is True
    assert feats["offline_default"] is False


def test_compute_features_no_anthropic_key_offline_by_default():
    """Without an Anthropic key, offline_default is True regardless of service health."""
    feats = clod._compute_features({}, _all_up())
    assert feats["offline_default"] is True
    assert feats["cloud_models"] is False


def test_compute_features_litellm_down():
    health = _all_up()
    health["litellm"] = False
    feats = clod._compute_features(_ENV_WITH_KEY, health)
    assert feats["cloud_models"] is False


def test_compute_features_searxng_down():
    health = _all_up()
    health["searxng"] = False
    feats = clod._compute_features({}, health)
    assert feats["web_search"] is False


def test_compute_features_chroma_down():
    health = _all_up()
    health["chroma"] = False
    feats = clod._compute_features({}, health)
    assert feats["semantic_recall"] is False


def test_compute_features_pipelines_down():
    health = _all_up()
    health["pipelines"] = False
    feats = clod._compute_features({}, health)
    assert feats["pipelines"] is False


def test_compute_features_all_down():
    feats = clod._compute_features({}, _all_down())
    assert feats["cloud_models"] is False
    assert feats["offline_default"] is True


# ── _check_service_health ──────────────────────────────────────────────────────


@resp_lib.activate
def test_check_service_health_all_up(mock_cfg):
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []}, status=200)
    resp_lib.add(resp_lib.GET, "http://localhost:4000/health", json={"status": "ok"}, status=200)
    resp_lib.add(resp_lib.GET, "http://localhost:9099/", json={}, status=200)
    resp_lib.add(resp_lib.GET, "http://localhost:8080/healthz", body="OK", status=200)
    resp_lib.add(resp_lib.GET, "http://localhost:8000/api/v2/heartbeat", json={}, status=200)

    health = clod._check_service_health(mock_cfg)
    assert health["ollama"] is True
    assert health["litellm"] is True
    assert health["pipelines"] is True
    assert health["searxng"] is True
    assert health["chroma"] is True


@resp_lib.activate
def test_check_service_health_all_down(mock_cfg):
    # No responses registered → all requests raise ConnectionError → all False
    health = clod._check_service_health(mock_cfg)
    assert health["ollama"] is False
    assert health["litellm"] is False
    assert health["pipelines"] is False
    assert health["searxng"] is False
    assert health["chroma"] is False


@resp_lib.activate
def test_check_service_health_partial(mock_cfg):
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", json={"models": []}, status=200)
    resp_lib.add(resp_lib.GET, "http://localhost:4000/health", status=500)
    # Others will raise ConnectionError (unregistered)

    health = clod._check_service_health(mock_cfg)
    assert health["ollama"] is True
    assert health["litellm"] is False


@resp_lib.activate
def test_check_service_health_5xx_is_down(mock_cfg):
    resp_lib.add(resp_lib.GET, "http://localhost:11434/api/tags", status=503)
    health = clod._check_service_health(mock_cfg)
    assert health["ollama"] is False


# ── _setup_env_wizard ──────────────────────────────────────────────────────────


def test_setup_env_wizard_creates_env(tmp_path, monkeypatch):
    """Wizard should create .env, write GPU_DRIVER, and return a dict."""
    monkeypatch.setattr(clod, "_get_clod_root", lambda: tmp_path)
    env_target = tmp_path / ".env"

    cfg = {"litellm_key": "sk-local-dev"}

    # Simulate user pressing Enter for all prompts (accept defaults, skip optional)
    inputs = iter(["", "", "", ""])  # gpu choice, anthropic key, hf token, litellm key

    class _FakeConsole:
        def print(self, *a, **kw):
            pass

        def input(self, *a, **kw):
            return next(inputs, "")

    monkeypatch.setattr(clod, "console", _FakeConsole())
    monkeypatch.setattr(clod, "save_config", lambda c: None)
    # Bypass shutil.copy2 (env.example may not exist in CI); just create blank target
    monkeypatch.setattr(clod.shutil, "copy2", lambda src, dst: pathlib.Path(dst).write_text(""))

    result = clod._setup_env_wizard(cfg)
    assert env_target.exists()
    assert isinstance(result, dict)


# ── pick_adapter with features ─────────────────────────────────────────────────


def test_pick_adapter_cloud_unavailable():
    """When cloud_models feature is off, pick_adapter returns 'cloud_unavailable'."""
    features = {"cloud_models": False}
    adapter = clod.pick_adapter("claude-sonnet", None, {}, features=features)
    assert adapter == "cloud_unavailable"


def test_pick_adapter_cloud_available():
    features = {"cloud_models": True}
    adapter = clod.pick_adapter("claude-sonnet", None, {}, features=features)
    assert adapter == "litellm"


def test_pick_adapter_no_features_defaults_to_litellm():
    """Without features dict, cloud model should still route to litellm (backward compat)."""
    adapter = clod.pick_adapter("claude-sonnet", None, {}, features=None)
    assert adapter == "litellm"


def test_pick_adapter_local_model_unaffected_by_features():
    features = {"cloud_models": False}
    adapter = clod.pick_adapter("qwen2.5-coder:14b", None, {}, features=features)
    assert adapter == "ollama"


def test_pick_adapter_pipeline_takes_priority():
    features = {"cloud_models": False}
    adapter = clod.pick_adapter("claude-sonnet", "code_review", {}, features=features)
    assert adapter == "pipeline"


# ── _get_clod_root ─────────────────────────────────────────────────────────────


def test_get_clod_root_not_frozen(monkeypatch):
    """In script mode (not frozen) returns the directory of clod.py."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    root = clod._get_clod_root()
    assert root == pathlib.Path(clod.__file__).parent


def test_get_clod_root_frozen(monkeypatch, tmp_path):
    """When frozen=True, returns the directory of the executable."""
    fake_exe = tmp_path / "clod.exe"
    fake_exe.write_text("")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    root = clod._get_clod_root()
    assert root == tmp_path


# ── _ensure_local_configs ──────────────────────────────────────────────────────


class _SilentConsole:
    """Console stub that records print calls but suppresses output."""

    def __init__(self):
        self.printed = []

    def print(self, *args, **kwargs):
        self.printed.append(args[0] if args else "")


@resp_lib.activate
def test_ensure_local_configs_present_skips(tmp_path):
    """Files that already exist should not trigger a GitHub fetch."""
    # Create the file
    cfg_file = tmp_path / "litellm" / "config.yaml"
    cfg_file.parent.mkdir()
    cfg_file.write_text("existing", encoding="utf-8")

    con = _SilentConsole()
    result = clod._ensure_local_configs(
        tmp_path, online_ok=True, console_obj=con, targets=["litellm/config.yaml"]
    )
    assert result == {"restored": [], "failed": []}
    # No HTTP requests should have been made
    assert len(resp_lib.calls) == 0


@resp_lib.activate
def test_ensure_local_configs_missing_fetches_github(tmp_path):
    """A missing file should be fetched from GitHub when online_ok=True."""
    content = b"# fetched config\n"
    resp_lib.add(
        resp_lib.GET,
        f"{clod._GITHUB_RAW_BASE}/litellm/config.yaml",
        body=content,
        status=200,
    )

    con = _SilentConsole()
    result = clod._ensure_local_configs(
        tmp_path, online_ok=True, console_obj=con, targets=["litellm/config.yaml"]
    )
    assert "litellm/config.yaml" in result["restored"]
    dest = tmp_path / "litellm" / "config.yaml"
    assert dest.exists()
    assert dest.read_bytes() == content


@resp_lib.activate
def test_ensure_local_configs_github_failure_warns(tmp_path):
    """A GitHub 404 should add the file to 'failed' and not create it."""
    resp_lib.add(
        resp_lib.GET,
        f"{clod._GITHUB_RAW_BASE}/litellm/config.yaml",
        status=404,
    )

    con = _SilentConsole()
    result = clod._ensure_local_configs(
        tmp_path, online_ok=True, console_obj=con, targets=["litellm/config.yaml"]
    )
    assert "litellm/config.yaml" in result["failed"]
    assert not (tmp_path / "litellm" / "config.yaml").exists()


@resp_lib.activate
def test_ensure_local_configs_offline_skips_github(tmp_path):
    """When online_ok=False, no GitHub request should be attempted."""
    con = _SilentConsole()
    result = clod._ensure_local_configs(
        tmp_path, online_ok=False, console_obj=con, targets=["litellm/config.yaml"]
    )
    assert "litellm/config.yaml" in result["failed"]
    assert len(resp_lib.calls) == 0


def test_ensure_local_configs_bundle_fallback(tmp_path, monkeypatch):
    """When frozen with a bundled file, it should be copied without GitHub fetch."""
    # Create a fake sys._MEIPASS with the bundled config
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    bundled_cfg = bundle_dir / "litellm" / "config.yaml"
    bundled_cfg.parent.mkdir(parents=True)
    bundled_cfg.write_text("# bundled", encoding="utf-8")

    fake_exe = tmp_path / "clod.exe"
    fake_exe.write_text("")
    dest_root = tmp_path / "install"
    dest_root.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_dir), raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)

    con = _SilentConsole()
    result = clod._ensure_local_configs(
        dest_root, online_ok=False, console_obj=con, targets=["litellm/config.yaml"]
    )
    assert "litellm/config.yaml" in result["restored"]
    assert (dest_root / "litellm" / "config.yaml").read_text() == "# bundled"


@resp_lib.activate
def test_ensure_local_configs_bundle_copy_exception_falls_to_github(tmp_path, monkeypatch):
    """If the bundle copy raises, fall through to GitHub fetch."""
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    bundled = bundle_dir / "litellm" / "config.yaml"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("# bundled")

    fake_exe = tmp_path / "clod.exe"
    fake_exe.write_text("")
    dest_root = tmp_path / "install"
    dest_root.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_dir), raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe), raising=False)
    # Make shutil.copy2 raise so the bundle path fails and GitHub is tried
    monkeypatch.setattr(
        clod.shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
    )

    resp_lib.add(
        resp_lib.GET,
        f"{clod._GITHUB_RAW_BASE}/litellm/config.yaml",
        body=b"# from github",
        status=200,
    )

    con = _SilentConsole()
    result = clod._ensure_local_configs(
        dest_root, online_ok=True, console_obj=con, targets=["litellm/config.yaml"]
    )
    # Bundle failed → GitHub succeeded
    assert "litellm/config.yaml" in result["restored"]


@resp_lib.activate
def test_ensure_local_configs_github_request_exception(tmp_path):
    """If requests.get raises (network error), file ends up in failed."""
    resp_lib.add(
        resp_lib.GET,
        f"{clod._GITHUB_RAW_BASE}/litellm/config.yaml",
        body=ConnectionError("no network"),
    )
    con = _SilentConsole()
    result = clod._ensure_local_configs(
        tmp_path, online_ok=True, console_obj=con, targets=["litellm/config.yaml"]
    )
    assert "litellm/config.yaml" in result["failed"]


# ── _offer_docker_startup ──────────────────────────────────────────────────────


class _InputConsole(_SilentConsole):
    """Console stub with configurable input response."""

    def __init__(self, input_val="n"):
        super().__init__()
        self._input_val = input_val

    def input(self, *a, **k):
        return self._input_val


def test_offer_docker_startup_user_declines(tmp_path, mock_cfg):
    """When user answers 'n', _offer_docker_startup returns False immediately."""
    mock_cfg["compose_file"] = str(tmp_path / "docker-compose.yml")
    result = clod._offer_docker_startup(mock_cfg, ["ollama"], _InputConsole("n"))
    assert result is False


def test_offer_docker_startup_compose_missing(tmp_path, mock_cfg):
    """If docker-compose.yml is absent, returns False after user confirms."""
    mock_cfg["compose_file"] = str(tmp_path / "nonexistent.yml")
    result = clod._offer_docker_startup(mock_cfg, ["ollama"], _InputConsole("y"))
    assert result is False


def test_offer_docker_startup_docker_not_found(tmp_path, monkeypatch, mock_cfg):
    """If docker CLI is not found, returns False."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")
    mock_cfg["compose_file"] = str(compose)

    def raise_fnf(*a, **k):
        raise FileNotFoundError("docker not found")

    monkeypatch.setattr(clod.subprocess, "run", raise_fnf)
    result = clod._offer_docker_startup(mock_cfg, ["ollama"], _InputConsole("y"))
    assert result is False


def test_offer_docker_startup_compose_nonzero(tmp_path, monkeypatch, mock_cfg):
    """If docker compose up returns non-zero, returns False."""
    import subprocess as _sp

    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")
    mock_cfg["compose_file"] = str(compose)

    fake_result = _sp.CompletedProcess(args=[], returncode=1, stdout="", stderr="fail")
    monkeypatch.setattr(clod.subprocess, "run", lambda *a, **k: fake_result)
    result = clod._offer_docker_startup(mock_cfg, ["ollama"], _InputConsole("y"))
    assert result is False


def test_offer_docker_startup_generic_exception(tmp_path, monkeypatch, mock_cfg):
    """Generic exceptions during docker compose up return False."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text("version: '3'")
    mock_cfg["compose_file"] = str(compose)

    monkeypatch.setattr(
        clod.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    result = clod._offer_docker_startup(mock_cfg, ["ollama"], _InputConsole("y"))
    assert result is False


# ── _setup_env_wizard extra branches ──────────────────────────────────────────


def test_setup_env_wizard_with_api_keys(tmp_path, monkeypatch):
    """Providing API keys covers the if-anthropic_key and if-hf_token branches."""
    monkeypatch.setattr(clod, "_get_clod_root", lambda: tmp_path)
    env_target = tmp_path / ".env"
    cfg = {"litellm_key": "sk-local-dev"}

    # 4 prompts: gpu_choice, anthropic_key, hf_token, litellm_key
    inputs = iter(["1", "sk-ant-test", "hf_test_token", ""])

    class _KeyedConsole:
        def print(self, *a, **k):
            pass

        def input(self, *a, **k):
            return next(inputs, "")

    monkeypatch.setattr(clod, "console", _KeyedConsole())
    monkeypatch.setattr(clod, "save_config", lambda c: None)
    monkeypatch.setattr(clod.shutil, "copy2", lambda src, dst: pathlib.Path(dst).write_text(""))
    monkeypatch.setattr(
        clod, "_ensure_local_configs", lambda *a, **k: {"restored": [], "failed": []}
    )

    result = clod._setup_env_wizard(cfg)
    assert env_target.exists()
    content = env_target.read_text()
    assert "ANTHROPIC_API_KEY" in content
    assert "HF_TOKEN" in content


def test_setup_env_wizard_write_exception(tmp_path, monkeypatch):
    """If .env cannot be written, wizard returns {}."""
    monkeypatch.setattr(clod, "_get_clod_root", lambda: tmp_path)
    cfg = {"litellm_key": "sk-local-dev"}

    inputs = iter(["", "", "", ""])

    class _C:
        def print(self, *a, **k):
            pass

        def input(self, *a, **k):
            return next(inputs, "")

    monkeypatch.setattr(clod, "console", _C())
    monkeypatch.setattr(clod, "save_config", lambda c: None)
    # Make copy2 raise to trigger the except → return {} branch
    monkeypatch.setattr(
        clod.shutil, "copy2", lambda *a, **k: (_ for _ in ()).throw(PermissionError("denied"))
    )
    # env_example does not exist so .exists() is False → write_text path
    # but we also need write_text to fail; patch write_text on the Path object
    original_write = pathlib.Path.write_text

    def fail_write(self, *a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(pathlib.Path, "write_text", fail_write)

    result = clod._setup_env_wizard(cfg)
    assert result == {}

    monkeypatch.setattr(pathlib.Path, "write_text", original_write)


# ── _get_service_volumes ───────────────────────────────────────────────────────


def test_get_service_volumes_yaml_parse(tmp_path, monkeypatch):
    """When docker-compose.yml is valid YAML, volumes are extracted correctly."""
    compose_content = """
services:
  ollama:
    volumes:
      - /host/ollama:/container:rw
  litellm:
    volumes:
      - type: bind
        source: /host/litellm
        target: /app
"""
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(compose_content)
    env_file = tmp_path / ".env"
    env_file.write_text("")

    cfg = {"compose_file": str(compose_file), "dotenv_file": str(env_file)}
    result = clod._get_service_volumes(cfg)

    assert "ollama" in result
    assert "litellm" in result
    assert "/host/litellm" in result["litellm"]


def test_get_service_volumes_fallback_when_yaml_fails(tmp_path, monkeypatch):
    """When YAML parsing fails (bad file), fallback to env-var resolution is used."""
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(": bad: yaml: [")
    env_file = tmp_path / ".env"
    env_file.write_text("OLLAMA_DATA_DIR=/mydata/ollama\nBASE_DIR=/mydata\n")

    cfg = {"compose_file": str(compose_file), "dotenv_file": str(env_file)}
    result = clod._get_service_volumes(cfg)

    # Fallback should return keys from _SERVICE_ENV_VOLUMES
    assert "ollama" in result


def test_get_service_volumes_env_var_expansion(tmp_path):
    """Env-var references like ${BASE_DIR} in volume paths are expanded."""
    compose_file = tmp_path / "docker-compose.yml"
    compose_file.write_text(": bad:")
    env_file = tmp_path / ".env"
    env_file.write_text("BASE_DIR=/base\nOLLAMA_DATA_DIR=${BASE_DIR}/ollama\n")

    cfg = {"compose_file": str(compose_file), "dotenv_file": str(env_file)}
    result = clod._get_service_volumes(cfg)
    ollama_paths = result.get("ollama", [])
    assert any("/base/ollama" in p for p in ollama_paths)
