"""
EXE smoke tests — run the compiled clod binary against its CLI surface
without a live LLM.

The EXE path is resolved from (in order):
  1. CLOD_EXE environment variable
  2. dist/clod.exe  (Windows)
  3. dist/clod      (Linux/macOS AppImage)

All tests are skipped when no binary is found (e.g. running unit tests locally
without a build).  In CI the exe-tests job sets CLOD_EXE explicitly.
"""

import http.server
import json
import os
import pathlib
import shutil
import socketserver
import subprocess
import sys
import threading

import pytest

# ── Locate the compiled binary ─────────────────────────────────────────────────

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


def _find_exe() -> pathlib.Path | None:
    if env := os.environ.get("CLOD_EXE"):
        return pathlib.Path(env)
    for name in ("dist/clod.exe", "dist/clod"):
        p = _REPO_ROOT / name
        if p.exists():
            return p
    return None


CLOD_EXE = _find_exe()

pytestmark = pytest.mark.skipif(
    CLOD_EXE is None,
    reason="Compiled clod binary not found — build first or set CLOD_EXE",
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _run_exe(args, env=None, timeout=30):
    return subprocess.run(
        [str(CLOD_EXE)] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _make_cfg_env(tmp_path, extra_cfg=None):
    """Write an isolated config.json and return an env dict pointing at it."""
    env = os.environ.copy()
    if sys.platform == "win32":
        config_dir = tmp_path / "clod"
        env["APPDATA"] = str(tmp_path)
    else:
        config_dir = tmp_path / ".config" / "clod"
        env["HOME"] = str(tmp_path)
        env.pop("APPDATA", None)
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "ollama_url": "http://127.0.0.1:1",
        "litellm_url": "http://127.0.0.1:1",
        "litellm_key": "sk-test",
        "pipelines_url": "http://127.0.0.1:1",
        "searxng_url": "http://127.0.0.1:1",
        "default_model": "qwen2.5-coder:14b",
        "token_budget": 10000,
    }
    if extra_cfg:
        cfg.update(extra_cfg)
    (config_dir / "config.json").write_text(json.dumps(cfg))
    return env


# ── Minimal mock Ollama server ─────────────────────────────────────────────────

_CHAT_BODY = json.dumps(
    {"message": {"role": "assistant", "content": "exe test response"}, "done": True}
)
_TAGS_BODY = json.dumps({"models": [{"name": "qwen2.5-coder:14b"}]})


def _start_mock_ollama():
    """Start a minimal Ollama-compatible HTTP server on a random port."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            body = _TAGS_BODY.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            body = _CHAT_BODY.encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    httpd = socketserver.TCPServer(("127.0.0.1", 0), _Handler)
    httpd.allow_reuse_address = True
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{port}"


# ── Tests ──────────────────────────────────────────────────────────────────────


def test_exe_version():
    """Binary exits 0 and reports its version string."""
    result = _run_exe(["--version"])
    assert result.returncode == 0
    assert "clod" in (result.stdout + result.stderr).lower()


def test_exe_help_exits_zero():
    """--help exits 0."""
    result = _run_exe(["--help"])
    assert result.returncode == 0


def test_exe_help_mentions_ollama():
    """--help output references Ollama (confirms help text is intact)."""
    result = _run_exe(["--help"])
    assert "ollama" in (result.stdout + result.stderr).lower()


def test_exe_help_mentions_pipeline():
    """--help output references pipeline commands."""
    result = _run_exe(["--help"])
    assert "pipeline" in (result.stdout + result.stderr).lower()


def test_exe_oneshot_mock_ollama(tmp_path):
    """EXE -p oneshot exits 0 and produces output against a mock Ollama server."""
    httpd, base_url = _start_mock_ollama()
    try:
        env = _make_cfg_env(tmp_path, {"ollama_url": base_url})
        result = _run_exe(["-p", "hi"], env=env, timeout=30)
        assert (
            result.returncode == 0
        ), f"Non-zero exit.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        assert len((result.stdout + result.stderr).strip()) > 0
    finally:
        httpd.shutdown()


def test_exe_clean_dir_seeds_config_files(tmp_path):
    """
    When the exe runs from a completely clean directory, _ensure_local_configs
    should seed docker-compose.yml and service config files from the bundle.

    Strategy:
      1. Copy clod.exe to an isolated temp directory (so _get_clod_root() = tmp_path).
      2. Run in -p (oneshot) mode — non-interactive, so no TTY prompts.
      3. Assert that docker-compose.yml and at least one service config file
         were created next to the exe.
    """
    exe_copy = tmp_path / "clod.exe"
    shutil.copy2(str(CLOD_EXE), str(exe_copy))

    httpd, base_url = _start_mock_ollama()
    try:
        env = _make_cfg_env(tmp_path, {"ollama_url": base_url})
        result = subprocess.run(
            [str(exe_copy), "-p", "hello"],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        combined = result.stdout + result.stderr

        # The exe may fail to reach Ollama (config files just restored, no service running),
        # but config files must have been seeded from the bundle.
        assert (
            tmp_path / "docker-compose.yml"
        ).exists(), (
            f"docker-compose.yml not created.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert (
            tmp_path / "litellm" / "config.yaml"
        ).exists(), "litellm/config.yaml not seeded from bundle."
        assert (
            tmp_path / "searxng" / "settings.yml"
        ).exists(), "searxng/settings.yml not seeded from bundle."
        assert (tmp_path / ".env.example").exists(), ".env.example not seeded from bundle."
    finally:
        httpd.shutdown()
