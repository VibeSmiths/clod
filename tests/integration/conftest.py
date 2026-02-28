"""
Integration-specific pytest fixtures: mock HTTP servers for Ollama and LiteLLM.
"""

import sys
import json
import pathlib
import threading
import http.server
import socketserver

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest

# ── Reusable handler factory ───────────────────────────────────────────────────


def _make_handler(routes: dict):
    """
    Return an HTTPRequestHandler class that dispatches POST/GET by path
    using the provided `routes` dict:
        {(method, path): (status_code, content_type, body_str)}
    """

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silence server log spam
            pass

        def _dispatch(self, method):
            key = (method, self.path)
            # Try exact match first, then prefix match
            entry = routes.get(key)
            if entry is None:
                # Try prefix match for paths with query strings, etc.
                for (m, p), v in routes.items():
                    if m == method and self.path.startswith(p):
                        entry = v
                        break
            if entry is None:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")
                return
            status, content_type, body = entry
            body_bytes = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body_bytes)))
            self.end_headers()
            self.wfile.write(body_bytes)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            # Consume request body so keep-alive doesn't stall
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            self._dispatch("POST")

    return _Handler


def _start_server(handler_cls):
    """
    Start an HTTPServer on a random free port in a daemon thread.
    Returns (httpd, base_url).
    """
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler_cls)
    httpd.allow_reuse_address = True
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{port}"


# ── Ollama mock ────────────────────────────────────────────────────────────────

_OLLAMA_CHAT_RESPONSE = json.dumps(
    {
        "message": {"role": "assistant", "content": "integration test response"},
        "done": True,
    }
)

_OLLAMA_TAGS_RESPONSE = json.dumps({"models": [{"name": "qwen2.5-coder:14b"}]})

_OLLAMA_ROUTES = {
    ("POST", "/api/chat"): (200, "application/x-ndjson", _OLLAMA_CHAT_RESPONSE),
    ("GET", "/api/tags"): (200, "application/json", _OLLAMA_TAGS_RESPONSE),
    # warmup also posts to /api/chat — covered by the entry above
}


@pytest.fixture(scope="session")
def mock_ollama_server():
    """Start a minimal Ollama-compatible HTTP server. Yields the base URL."""
    handler = _make_handler(_OLLAMA_ROUTES)
    httpd, base_url = _start_server(handler)
    yield base_url
    httpd.shutdown()


# ── LiteLLM mock ──────────────────────────────────────────────────────────────

_LITELLM_SSE = (
    'data: {"choices": [{"delta": {"content": "test"}, "finish_reason": null}]}\n\n'
    "data: [DONE]\n\n"
)

_LITELLM_ROUTES = {
    ("POST", "/v1/chat/completions"): (200, "text/event-stream", _LITELLM_SSE),
}


@pytest.fixture(scope="session")
def mock_litellm_server():
    """Start a minimal LiteLLM-compatible HTTP server. Yields the base URL."""
    handler = _make_handler(_LITELLM_ROUTES)
    httpd, base_url = _start_server(handler)
    yield base_url
    httpd.shutdown()


# ── Combined config fixture ────────────────────────────────────────────────────


@pytest.fixture
def integration_cfg(mock_ollama_server, mock_litellm_server):
    """Config dict pointing at both mock servers."""
    return {
        "ollama_url": mock_ollama_server,
        "litellm_url": mock_litellm_server,
        "litellm_key": "sk-test",
        "pipelines_url": mock_litellm_server,  # reuse litellm mock for pipelines
        "searxng_url": "http://127.0.0.1:1",  # unused in inference tests
        "default_model": "qwen2.5-coder:14b",
        "pipeline": None,
        "enable_tools": False,
        "token_budget": 10000,
    }
