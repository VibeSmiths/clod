"""
Integration tests that invoke clod.py as a subprocess.
"""

import sys
import os
import json
import pathlib
import subprocess

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest

# Absolute path to clod.py (three levels up from this file)
CLOD_PY = pathlib.Path(__file__).parent.parent.parent / "clod.py"


def _run(args, env=None, input_text=None, timeout=30):
    """Helper: run clod.py with the given args, return CompletedProcess."""
    cmd = [sys.executable, str(CLOD_PY)] + args
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        input=input_text,
    )


def _env_with_config(tmp_path, extra_cfg=None):
    """
    Return an env dict that points APPDATA (Windows) / HOME (Linux)
    to tmp_path so that clod reads config from there.
    Also writes a config.json at the expected location.
    """
    env = os.environ.copy()

    if sys.platform == "win32":
        config_dir = tmp_path / "clod"
        env["APPDATA"] = str(tmp_path)
    else:
        config_dir = tmp_path / ".config" / "clod"
        env["HOME"] = str(tmp_path)
        # Unset APPDATA if set, so Linux path is used
        env.pop("APPDATA", None)

    config_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "ollama_url": "http://127.0.0.1:1",  # unreachable — overridden per test
        "litellm_url": "http://127.0.0.1:1",
        "litellm_key": "sk-test",
        "pipelines_url": "http://127.0.0.1:1",
        "searxng_url": "http://127.0.0.1:1",
        "default_model": "qwen2.5-coder:14b",
        "pipeline": None,
        "enable_tools": False,
        "token_budget": 10000,
    }
    if extra_cfg:
        cfg.update(extra_cfg)
    (config_dir / "config.json").write_text(json.dumps(cfg))
    return env


# ── Flag tests (no network needed) ────────────────────────────────────────────


def test_version_flag():
    """clod.py --version outputs a string containing 'clod'."""
    result = _run(["--version"])
    output = result.stdout + result.stderr
    assert "clod" in output.lower()


def test_help_flag():
    """clod.py --help output mentions 'ollama' (case insensitive)."""
    result = _run(["--help"])
    output = (result.stdout + result.stderr).lower()
    assert "ollama" in output


# ── Oneshot against mock Ollama ────────────────────────────────────────────────


def test_oneshot_against_mock_ollama(mock_ollama_server, tmp_path):
    """
    Running clod.py -p 'hi' with config pointing at the mock Ollama
    server should exit 0 and produce some output.
    """
    env = _env_with_config(tmp_path, {"ollama_url": mock_ollama_server})
    result = _run(["-p", "hi"], env=env, timeout=30)
    output = result.stdout + result.stderr
    assert result.returncode == 0, f"Non-zero exit.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert len(output.strip()) > 0


# ── Index mode ─────────────────────────────────────────────────────────────────


def test_index_mode_creates_files(mock_ollama_server, tmp_path):
    """
    Running clod.py --index <dir> against a mock Ollama server creates
    CLAUDE.md and README.md in the project directory.
    """
    # Create a minimal project directory
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / "requirements.txt").write_text("requests\n")

    env = _env_with_config(tmp_path, {"ollama_url": mock_ollama_server})

    # Use a separate home dir for config (don't pollute project_dir)
    result = _run(["--index", str(project_dir)], env=env, timeout=60)

    # The command should complete without error
    assert result.returncode == 0, (
        f"Non-zero exit.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )

    # CLAUDE.md and README.md should have been written
    assert (project_dir / "CLAUDE.md").exists(), "CLAUDE.md was not created"
    assert (project_dir / "README.md").exists(), "README.md was not created"
