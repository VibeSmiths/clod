# Testing Patterns

**Analysis Date:** 2026-03-10

## Test Framework

**Runner:**
- pytest
- Config: `pyproject.toml`
- Traceback format: short (`--tb=short`)
- Test paths: `tests/` directory

**Assertion Library:**
- pytest built-in assertions
- No external assertion library

**Run Commands:**
```bash
python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing
python -m pytest tests/ -k "test_name"
python -m pytest tests/integration/ --tb=short
```

**Coverage:**
- Target: ~76% (307 tests, some untestable lines due to TTY/interactive code)
- Source: `clod` module only
- Exclusions: `tests/*`, `scripts/*`, `rthooks/*`
- Excluded lines: `pragma: no cover`, `if __name__ == '__main__'`, `raise NotImplementedError`, `pass`
- Coverage report: `--cov-report=term-missing` shows missing lines

## Test File Organization

**Location:**
- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- Shared fixtures: `tests/conftest.py`

**Naming:**
- `test_<module>.py` (e.g., `test_config.py`, `test_startup.py`)
- Within files: `test_<function>_<scenario>` (e.g., `test_load_config_returns_defaults`)

**Structure:**
```
tests/
├── conftest.py                    # Shared fixtures
├── unit/
│   ├── test_config.py             # Config loading/saving
│   ├── test_startup.py            # Env, health checks, feature flags
│   ├── test_model_routing.py      # pick_adapter logic
│   ├── test_ollama_mgmt.py        # Ollama operations
│   ├── test_stream.py             # Streaming backends
│   ├── test_slash.py              # REPL slash commands
│   ├── test_slash_extended.py     # Extended slash command coverage
│   ├── test_tools.py              # Tool executors
│   ├── test_tools_extended.py     # Extended tool coverage
│   ├── test_main.py               # Main entry point
│   ├── test_mcp_and_banner.py     # MCP server, banner printing
│   ├── test_project_detection.py  # Project type detection
│   ├── test_sd_switch_and_video.py # Stable Diffusion/ComfyUI
│   ├── test_token_budget.py       # TokenBudget class
│   ├── test_infer.py              # Inference loop
│   ├── test_ui.py                 # UI helpers
│   ├── test_indexer_extended.py   # Project indexing
│   ├── test_coverage_gaps.py      # Edge cases, error paths
│   └── __init__.py
└── integration/
    ├── conftest.py                # Integration fixtures
    ├── test_exe.py                # .exe binary tests (Windows)
    ├── test_subprocess.py         # subprocess invocation
    ├── test_inference.py          # End-to-end inference
    └── __init__.py
```

## Test Structure

**Suite Organization:**
```python
"""
Unit tests for [module/function].
"""

import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod

# ── Section Name ────────────────────────────────────

def test_function_expected_behavior(fixture_name):
    """Docstring describes test scenario."""
    # Arrange / Setup
    data = {"key": "value"}

    # Act / Execute
    result = clod.some_function(data)

    # Assert / Verify
    assert result == expected
```

**Patterns:**
- Setup: Use fixtures for common test data
- Teardown: Fixtures with `yield` for cleanup
- Assertions: Single assertion per test (or grouped related assertions)

## Mocking

**Framework:** `responses` library for HTTP mocking (imported as `resp_lib`)

**Patterns:**
```python
import responses as resp_lib

@resp_lib.activate
def test_function(mock_cfg):
    """HTTP calls are intercepted and mocked."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        json={"models": [{"name": "model:tag"}]},
        status=200,
    )

    result = clod.function_under_test(mock_cfg)
    assert result is not None
```

**Exception mocking:**
```python
@resp_lib.activate
def test_connection_error(mock_cfg):
    """Simulates connection failure."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        body=requests.exceptions.ConnectionError(),
    )

    result = clod.function_under_test(mock_cfg)
    # Assert graceful handling
```

**monkeypatch usage:**
```python
def test_model_warmup(monkeypatch, mock_cfg):
    """Intercept function calls."""
    calls = []

    monkeypatch.setattr(
        clod,
        "warmup_ollama_model",
        lambda model, cfg: calls.append(model),
    )

    clod.pick_adapter("qwen2.5-coder:14b", None, mock_cfg)
    assert "qwen2.5-coder:14b" in calls
```

**What to Mock:**
- HTTP requests (all external API calls)
- File I/O for config paths (`monkeypatch.setattr(clod, "config_path", lambda: tmp_path / "test.json")`)
- Global objects (e.g., `clod.console` → `FakeConsole`)

**What NOT to Mock:**
- Business logic functions (test the real implementation)
- Internal helper functions
- Config dict structures (use `mock_cfg` fixture instead)

## Fixtures and Factories

**Test Data (from `tests/conftest.py`):**

```python
@pytest.fixture
def fake_console(monkeypatch):
    """Monkeypatch clod.console with a no-op object."""
    class _FakeConsole:
        def print(self, *args, **kwargs):
            pass
        def input(self, *args, **kwargs):
            return ""
        def status(self, *args, **kwargs):
            import contextlib
            return contextlib.nullcontext()

    fc = _FakeConsole()
    monkeypatch.setattr(clod, "console", fc)
    return fc

@pytest.fixture
def mock_cfg():
    """Return a minimal config dict with localhost URLs."""
    return {
        "ollama_url": "http://localhost:11434",
        "litellm_url": "http://localhost:4000",
        "litellm_key": "sk-local-dev",
        "pipelines_url": "http://localhost:9099",
        "searxng_url": "http://localhost:8080",
        "default_model": "qwen2.5-coder:14b",
        "pipeline": None,
        "enable_tools": False,
        "token_budget": 10000,
    }

@pytest.fixture
def mock_session_state(mock_cfg):
    """Return a complete session_state dict suitable for REPL tests."""
    return {
        "model": "qwen2.5-coder:14b",
        "pipeline": None,
        "tools_on": False,
        "system": None,
        "cfg": mock_cfg,
        "budget": clod.TokenBudget(10000),
        "offline": False,
    }
```

**Location:**
- Shared fixtures: `tests/conftest.py`
- Test-specific fixtures: defined in test file with `@pytest.fixture`
- Temporary files: pytest's `tmp_path` fixture

**Factory pattern (in tests):**
```python
def _make_state(mock_cfg):
    """Return a fresh, complete session_state dict."""
    return {
        "model": "qwen2.5-coder:14b",
        "pipeline": None,
        "tools_on": False,
        "system": None,
        "cfg": mock_cfg,
        "budget": clod.TokenBudget(10000),
        "offline": False,
    }

def test_feature(mock_cfg):
    state = _make_state(mock_cfg)
    # test with state
```

## Coverage

**Requirements:** ~76% target (some code untestable due to TTY/interactive context)

**View Coverage:**
```bash
python -m pytest tests/unit/ --cov=clod --cov-report=term-missing
```

**Untestable lines (~6% of codebase):**
- Lines 35-36: `HAS_PSUTIL = False` (import error at module level)
- Lines 1703-1782: `run_repl()` (requires interactive TTY + prompt_toolkit)
- Lines 1854-1866: `--auto-model` CLI path in `main()`
- Line 1890: `run_repl()` call in `main()`

## Test Types

**Unit Tests:**
- Scope: Single function or small component in isolation
- Location: `tests/unit/`
- Framework: pytest with mocked HTTP/file I/O
- Example: `test_pick_adapter_ollama()` — tests model routing logic only
- Count: ~307 tests across 16 unit test files

**Integration Tests:**
- Scope: Multiple components working together
- Location: `tests/integration/`
- Framework: pytest, may invoke subprocess or compiled binary
- Example: `test_exe.py` — tests compiled `.exe` against real services (Windows)
- Example: `test_subprocess.py` — tests `clod.py` via subprocess
- Skips: Skipped if required binary/service unavailable

**E2E Tests:**
- Not yet implemented; integration tests serve as closest equivalent
- Would test full REPL flow with real services

## Common Patterns

**Async Testing:**
- Not applicable (no async code in codebase)

**Error Testing:**
```python
def test_tool_read_file_missing():
    """Reading a non-existent file returns an error message."""
    result = tool_read_file({"path": "/nonexistent/path/to/file.txt"})
    assert "not found" in result.lower() or "error" in result.lower()

def test_ollama_local_models_connection_error(mock_cfg):
    """ConnectionError returns an empty list (no exception raised)."""
    resp_lib.add(
        resp_lib.GET,
        "http://localhost:11434/api/tags",
        body=requests.exceptions.ConnectionError(),
    )
    models = clod.ollama_local_models(mock_cfg["ollama_url"])
    assert models == []
```

**Streaming Testing:**
```python
@resp_lib.activate
def test_stream_ollama_tokens(mock_cfg):
    """Normal two-chunk stream yields two token events followed by done."""
    body = (
        b'{"message": {"content": "hello "}, "done": false}\n'
        b'{"message": {"content": "world"}, "done": true}\n'
    )
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/chat", body=body)

    events = list(clod.stream_ollama([{"role": "user", "content": "hi"}], "m", mock_cfg))
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert tokens == ["hello ", "world"]
```

**Feature flag testing:**
```python
def _all_up():
    return {"ollama": True, "litellm": True, "pipelines": True, "searxng": True, "chroma": True}

def test_compute_features_all_healthy():
    feats = clod._compute_features({"ANTHROPIC_API_KEY": "sk-ant-test"}, _all_up())
    assert feats["cloud_models"] is True
    assert feats["offline_default"] is False

def test_compute_features_no_anthropic_key_offline_by_default():
    """Without an Anthropic key, offline_default is True regardless of service health."""
    feats = clod._compute_features({}, _all_up())
    assert feats["offline_default"] is True
```

## Test Execution

**CI/CD Integration:**
- Pipeline: `.github/workflows/pipeline.yml`
- Stages: lint → unit-tests → build → integration-tests → release
- Unit tests run on all PRs
- Integration tests run on Linux (non-PR) and Windows (exe-tests)
- Coverage checked but no hard threshold enforced

---

*Testing analysis: 2026-03-10*
