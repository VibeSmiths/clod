# Phase 6: Docker Service Integration & Testing - Research

**Researched:** 2026-03-10
**Domain:** Python testing (pytest), HTTP mocking, subprocess mocking, CI coverage gates
**Confidence:** HIGH

## Summary

Phase 6 is a pure testing phase -- no new production code. The goal is to write comprehensive mocked tests for all Docker service lifecycle functions (`_check_service_health`, `_offer_docker_startup`, `_compose_base`, `/services start|stop|reset`, `_get_service_volumes`, `_reset_service`, `_setup_env_wizard`, `_ensure_local_configs`) and the generation pipeline orchestrator (`_handle_generation_intent`), plus consolidate `tests/integration/test_inference.py` into `tests/unit/` and add `--cov-fail-under=90` to CI.

The project already has a mature testing infrastructure: 455 tests in `tests/unit/`, the `responses` library for HTTP mocking, `monkeypatch` for subprocess patching, `FakeConsole` for Rich console suppression, and existing fixtures (`mock_cfg`, `mock_session_state`, `mock_generation_state`) in `tests/conftest.py`. The existing `test_startup.py` (43 tests) already covers `_parse_dotenv`, `_compute_features`, `_check_service_health`, `_setup_env_wizard`, `_get_service_volumes`, `_ensure_local_configs`, `_offer_docker_startup`, and `pick_adapter` with features. Existing `test_generation_repl.py` covers `_handle_generation_intent` full flows. The main gaps are: (1) `/services` slash command routing (start/stop/reset sub-commands via `handle_slash`), (2) `_reset_service` function directly, (3) E2E generation failure scenarios with file output verification, and (4) CI pipeline coverage gate.

**Primary recommendation:** Write 2-3 new test files targeting `/services` slash command routing, `_reset_service` direct testing, and generation E2E failure scenarios. Consolidate `test_inference.py` into unit tests. Add `--cov-fail-under=90` to `pipeline.yml`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- All tests fully mocked -- no Docker Desktop required. HTTP mocking via `responses` library, subprocess mocking via `monkeypatch`
- Docker CLI commands (docker compose up, docker ps) mocked at subprocess level -- patch `subprocess.run` to return fake docker output
- Tests go in `tests/unit/` alongside existing unit tests -- since everything is mocked, they're effectively unit tests
- Target: 90%+ test coverage (currently ~85% with 455 tests)
- Test ALL Docker service operations: `_check_service_health`, `_offer_docker_startup`, `_compose_base`, `/services start|stop|reset`, `_get_service_volumes`, `_reset_service`, `_setup_env_wizard`, `_ensure_local_configs`
- Test both layers: handle_slash('/services ...') for command parsing/routing AND underlying functions directly for logic
- `_setup_env_wizard`: mock all console.input() prompts -- test happy path (user provides key), skip path (enter), and .env.example missing path
- `_ensure_local_configs`: test local bundled restore path only -- skip GitHub fallback HTTP testing
- Full flow E2E tests for `_handle_generation_intent`: intent -> VRAM handoff -> craft prompt -> generate -> save -> restore, with all dependencies mocked
- Verify actual file output -- write fake PNG/video bytes, assert file appears at expected path with `clod_{timestamp}_{hash}.ext` naming, using `tmp_path` fixture
- Dedicated E2E test for Docker profile switch flow: detect wrong profile -> confirm -> stop current -> verify VRAM -> start new -> poll health
- Test key failure scenarios: service unreachable during generation, VRAM verification timeout, docker compose failure -- verify graceful degradation and error messages
- No special handling needed -- fully mocked tests run in existing `python -m pytest tests/unit/` CI step
- Add `--cov-fail-under=90` to CI pipeline to enforce coverage threshold
- Consolidate `tests/integration/test_inference.py` into `tests/unit/` (it uses HTTP mocks, not real services). Keep `test_exe.py` separate (needs compiled binary)
- Update `.github/workflows/pipeline.yml`: add coverage gate, adjust integration-tests job to only run exe tests

### Claude's Discretion
- Exact test file organization within tests/unit/ (how many test files, naming)
- Which specific failure scenarios to E2E test (pick 3-4 most impactful)
- How to consolidate test_inference.py (merge into existing test file or rename)
- Mock fixture design for subprocess.run Docker commands

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=7.4 | Test framework | Already in requirements-dev.txt, used by all 455 existing tests |
| pytest-cov | >=4.1 | Coverage reporting | Already in requirements-dev.txt, powers CI coverage reports |
| responses | >=0.24 | HTTP mock library | Already in requirements-dev.txt, used in 20+ test files |
| coverage[toml] | >=7.2 | Coverage engine | Already in requirements-dev.txt |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unittest.mock | stdlib | patch/MagicMock for subprocess | Already used in test_generation_repl.py, test_generation_video.py |
| monkeypatch | pytest builtin | setattr/delattr for function patching | Already used extensively in test_startup.py |
| tmp_path | pytest builtin | Temporary directory fixture | Already used in test_generation.py for file output verification |

**Installation:** No new dependencies needed -- everything is already in `requirements-dev.txt`.

## Architecture Patterns

### Recommended Test File Organization

```
tests/unit/
  test_services_slash.py       # NEW: /services start|stop|reset via handle_slash()
  test_docker_lifecycle.py     # NEW: _reset_service, _compose_base, profile switch E2E
  test_generation_e2e.py       # NEW: generation failure scenarios with file output
  test_inference_unit.py       # MOVED: from tests/integration/test_inference.py
  test_startup.py              # EXISTING: keep as-is (43 tests already cover most startup helpers)
  test_generation.py           # EXISTING: keep as-is
  test_generation_repl.py      # EXISTING: keep as-is (full flow E2E already tested)
  test_generation_video.py     # EXISTING: keep as-is
```

### Pattern 1: Subprocess Mock Fixture for Docker Commands

**What:** A reusable fixture that intercepts `subprocess.run` calls and returns configurable `CompletedProcess` results based on command arguments.
**When to use:** All tests that exercise Docker compose operations (`_reset_service`, `/services stop`, `_offer_docker_startup`).

```python
import subprocess as _sp

@pytest.fixture
def mock_subprocess(monkeypatch):
    """Mock subprocess.run to return configurable results for docker commands."""
    results = {}  # (command_suffix,) -> CompletedProcess

    def _fake_run(cmd, *args, **kwargs):
        # Match on the docker compose subcommand (last meaningful args)
        # e.g., ["docker", "compose", "-f", "x.yml", "stop", "ollama"] -> ("stop", "ollama")
        docker_args = tuple(a for a in cmd if not a.startswith("-") and a not in ("docker", "compose"))
        for key, result in results.items():
            if all(k in docker_args for k in key):
                return result
        # Default: success
        return _sp.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(clod.subprocess, "run", _fake_run)
    return results  # caller populates with expected results
```

### Pattern 2: handle_slash Service Tests

**What:** Test `/services` sub-commands through `handle_slash()` with mocked dependencies.
**When to use:** Testing command routing, session_state updates, and user interaction flows.

```python
@responses.activate
def test_services_start_all_running(fake_console, mock_session_state):
    """When all services are up, /services start prints success message."""
    # Mock all health endpoints as healthy
    for url, path in SERVICE_HEALTH_ENDPOINTS:
        responses.add(responses.GET, f"{url}{path}", status=200, json={})

    mock_session_state["cfg"]["compose_file"] = "/tmp/docker-compose.yml"
    mock_session_state["cfg"]["dotenv_file"] = "/tmp/.env"

    result = clod.handle_slash("/services start", mock_session_state, [])
    assert result is True
```

### Pattern 3: File Output Verification with tmp_path

**What:** Write fake binary content, verify file naming pattern `clod_{date}_{time}_{hash}.{ext}`.
**When to use:** Generation E2E tests that verify actual file output.

```python
def test_generation_saves_file(tmp_path, mock_session, fake_console, mock_cfg):
    mock_cfg["sd_output_dir"] = str(tmp_path)
    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50

    with patch("clod._generate_image") as m_gen:
        # Have _generate_image write a real file
        def write_and_return(*args, **kwargs):
            return clod._save_generation_output(fake_png, "png", str(tmp_path))
        m_gen.side_effect = write_and_return
        # ... trigger generation ...

    files = list(tmp_path.glob("clod_*.png"))
    assert len(files) == 1
    assert files[0].read_bytes() == fake_png
```

### Anti-Patterns to Avoid
- **Duplicating existing tests:** `test_startup.py` already has 43 tests covering `_parse_dotenv`, `_compute_features`, `_check_service_health`, `_setup_env_wizard`, `_get_service_volumes`, `_ensure_local_configs`, `_offer_docker_startup`, and `pick_adapter`. Do NOT re-test these -- focus on the gaps.
- **Testing implementation details:** Do not assert on exact Rich markup strings. Assert on behavior (return values, side effects, file existence).
- **Redefining FakeConsole per file:** Generation test files already define their own `fake_console` fixtures. For new test files, prefer using the one from `tests/conftest.py` unless you need custom behavior (like recording printed output or configurable `input()` returns).
- **Forgetting try/finally in generation tests:** The production code uses try/finally to ensure model restore. Tests should verify this behavior by checking `_silent_restore_model` is called even on failure.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP mocking | Custom httpserver | `responses` library with `@responses.activate` | Already used in 20+ files, handles connection errors, status codes |
| Console suppression | StringIO wrapper | `FakeConsole` from `tests/conftest.py` | Already handles Rich Progress/Live/Status components |
| Temp file cleanup | Manual rmtree | pytest `tmp_path` fixture | Automatic per-test cleanup, cross-platform |
| Function patching | Manual mock objects | `monkeypatch.setattr(clod, "fn", ...)` or `@patch("clod.fn")` | Consistent with existing patterns |

## Common Pitfalls

### Pitfall 1: Session State Mutation Between Tests
**What goes wrong:** `/services` handlers mutate `session_state` in place (setting `features`, `health`, `offline`). If fixtures are shared, state leaks between tests.
**Why it happens:** `mock_session_state` from conftest.py is a dict (mutable). Tests that call `handle_slash("/services stop", ...)` will modify `session_state["offline"] = True`.
**How to avoid:** Always use a fresh fixture per test (pytest creates new fixture instances per test by default). Never use `scope="module"` or `scope="session"` for mutable state fixtures.
**Warning signs:** Tests pass individually but fail when run together.

### Pitfall 2: Missing compose_file/dotenv_file in mock_cfg
**What goes wrong:** Many service functions access `cfg.get("compose_file")` and `cfg.get("dotenv_file")`. The default `mock_cfg` from conftest.py does NOT include these keys.
**Why it happens:** `mock_cfg` was written for earlier phases that didn't need compose paths.
**How to avoid:** Either extend `mock_cfg` or create a dedicated `service_cfg` fixture that includes `compose_file` and `dotenv_file` pointing to `tmp_path` files.

### Pitfall 3: responses Library Requires Exact URL Matching
**What goes wrong:** `_check_service_health` hits specific endpoints like `/api/tags`, `/health`, `/healthz`, `/api/v2/heartbeat`. Missing even one mock URL causes `ConnectionError`.
**Why it happens:** `responses` raises `ConnectionError` for unregistered URLs by default.
**How to avoid:** For `/services start` tests, register all 5 health check URLs. The existing `test_startup.py::test_check_service_health_all_up` shows the exact endpoints.

### Pitfall 4: subprocess.run Patching Scope
**What goes wrong:** Patching `subprocess.run` globally affects ALL subprocess calls, including any pytest internals.
**Why it happens:** `monkeypatch.setattr(clod.subprocess, "run", ...)` patches the `subprocess` module reference inside `clod`, which is the correct scope.
**How to avoid:** Always patch `clod.subprocess.run`, NOT `subprocess.run`. The existing `test_startup.py` already does this correctly.

### Pitfall 5: Coverage Gate May Fail Initially
**What goes wrong:** Adding `--cov-fail-under=90` to CI when current coverage is ~85% will break the build.
**Why it happens:** The coverage gate is added before the new tests that push coverage above 90%.
**How to avoid:** Add the coverage gate in the same PR/commit that adds the new tests. Or set `--cov-fail-under=85` initially and increase after verifying the new tests land.

## Code Examples

### Health Check Endpoint Reference
```python
# From test_startup.py -- the exact endpoints _check_service_health hits:
# Source: tests/unit/test_startup.py lines 139-152
responses.add(responses.GET, "http://localhost:11434/api/tags", json={"models": []}, status=200)    # ollama
responses.add(responses.GET, "http://localhost:4000/health", json={"status": "ok"}, status=200)      # litellm
responses.add(responses.GET, "http://localhost:9099/", json={}, status=200)                          # pipelines
responses.add(responses.GET, "http://localhost:8080/healthz", body="OK", status=200)                 # searxng
responses.add(responses.GET, "http://localhost:8000/api/v2/heartbeat", json={}, status=200)          # chroma
```

### _InputConsole Pattern for Configurable User Input
```python
# From test_startup.py -- reusable pattern for testing interactive prompts:
# Source: tests/unit/test_startup.py lines 427-435
class _InputConsole(_SilentConsole):
    """Console stub with configurable input response."""
    def __init__(self, input_val="n"):
        super().__init__()
        self._input_val = input_val
    def input(self, *a, **k):
        return self._input_val
```

### subprocess.run Mock Pattern
```python
# From test_startup.py -- mocking docker compose commands:
# Source: tests/unit/test_startup.py lines 466-477
import subprocess as _sp

fake_result = _sp.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
monkeypatch.setattr(clod.subprocess, "run", lambda *a, **k: fake_result)
```

### Generation Intent Full Flow with Patches
```python
# From test_generation_repl.py -- the established pattern for E2E gen tests:
# Source: tests/unit/test_generation_repl.py lines 87-123
@patch("clod._silent_restore_model")
@patch("os.startfile", create=True)
@patch("clod._generate_image", return_value="/tmp/clod_img.png")
@patch("clod._get_negative_prompts", return_value="bad quality")
@patch("clod._detect_sd_model_type", return_value="sd15")
@patch("clod._ensure_generation_service", return_value=True)
@patch("clod._unload_model", return_value=True)
@patch("clod._craft_sd_prompt", return_value=("a beautiful sunset", "blur"))
@patch("clod._ensure_model_ready", return_value=True)
def test_handle_generation_intent_image_full_flow(m_ensure, m_craft, ...):
    clod._handle_generation_intent("image_gen", "a sunset", mock_session, fake_console, mock_cfg)
    m_restore.assert_called_once()  # model always restored
```

## Coverage Gap Analysis

### Currently Tested (from existing test files)
| Function | Test File | Tests |
|----------|-----------|-------|
| `_parse_dotenv` | test_startup.py | 5 tests |
| `_compute_features` | test_startup.py | 8 tests |
| `_check_service_health` | test_startup.py | 4 tests |
| `_setup_env_wizard` | test_startup.py | 3 tests |
| `_get_service_volumes` | test_startup.py | 3 tests |
| `_ensure_local_configs` | test_startup.py | 7 tests |
| `_offer_docker_startup` | test_startup.py | 5 tests |
| `_get_clod_root` | test_startup.py | 2 tests |
| `pick_adapter` (features) | test_startup.py | 5 tests |
| `_handle_generation_intent` | test_generation_repl.py | 7 tests |
| `_ensure_generation_service` | test_generation_video.py | 5 tests |
| `_silent_restore_model` | test_generation_video.py | 2 tests |
| `_craft_sd_prompt` | test_generation.py | 4 tests |
| `_generate_image` | test_generation.py | 3 tests |
| `_generate_video` | test_generation_video.py | 3 tests |
| `infer()` (integration) | tests/integration/test_inference.py | 4 tests |

### NOT Tested (gaps this phase must fill)
| Function/Feature | Why Missing | Priority |
|------------------|-------------|----------|
| `handle_slash("/services")` (status) | No tests exist for /services routing | HIGH |
| `handle_slash("/services start")` | No tests | HIGH |
| `handle_slash("/services stop")` | No tests | HIGH |
| `handle_slash("/services reset ...")` | No tests | HIGH |
| `_reset_service` (direct) | No tests | HIGH |
| `_compose_base` | No tests | MEDIUM |
| Generation with actual file output | Existing tests mock `_generate_image` return value but don't verify file write | MEDIUM |
| Profile switch E2E | `_ensure_generation_service` tested but not full profile switch flow | MEDIUM |
| `sd_switch_mode` | Tested in test_sd_switch_and_video.py but not via generation flow | LOW |

### test_inference.py Consolidation
The `tests/integration/test_inference.py` file contains 4 tests that use `responses`-style HTTP mock servers (via `conftest.py` which starts `http.server` on random ports). These are effectively unit tests with a slightly heavier mock setup. Consolidation approach:
- Move tests to `tests/unit/test_inference_unit.py`
- Replace the `http.server` mock fixtures with `@responses.activate` decorators (matching existing unit test patterns)
- Delete `tests/integration/test_inference.py` and its custom `conftest.py` fixtures (`mock_ollama_server`, `mock_litellm_server`, `integration_cfg`)
- Keep `tests/integration/test_exe.py` and `tests/integration/test_subprocess.py` as-is

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Real Docker in CI | Fully mocked tests | Phase 6 decision | No Docker Desktop needed in CI |
| No coverage gate | `--cov-fail-under=90` | Phase 6 | Prevents coverage regression |
| Mock HTTP servers (http.server) | `responses` library | Already migrated for unit tests | Simpler, more reliable mocking |

## Open Questions

1. **Exact current coverage percentage**
   - What we know: ~85% with 455 tests (from CONTEXT.md), recently added generation tests
   - What's unclear: Exact line-by-line coverage report was not obtained (test run timed out)
   - Recommendation: Run `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` at start of implementation to baseline

2. **Integration test job scope after consolidation**
   - What we know: `tests/integration/test_inference.py` moves to unit tests. `test_exe.py` stays. `test_subprocess.py` stays.
   - What's unclear: Whether `integration-tests` CI job should still run `pytest tests/integration/` (which would now only have test_subprocess.py + test_exe.py)
   - Recommendation: Keep `integration-tests` job running `pytest tests/integration/` -- test_subprocess.py still needs it. Only `exe-tests` stays Windows-specific.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.4 + pytest-cov >=4.1 |
| Config file | pyproject.toml (coverage settings) or pytest.ini if exists |
| Quick run command | `python -m pytest tests/unit/ -q --tb=short` |
| Full suite command | `python -m pytest tests/unit/ -v --cov=clod --cov-report=term-missing --cov-fail-under=90` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| N/A (testing phase) | /services start routes correctly | unit | `pytest tests/unit/test_services_slash.py -x` | Wave 0 |
| N/A | /services stop routes correctly | unit | `pytest tests/unit/test_services_slash.py -x` | Wave 0 |
| N/A | /services reset routes correctly | unit | `pytest tests/unit/test_services_slash.py -x` | Wave 0 |
| N/A | _reset_service handles all branches | unit | `pytest tests/unit/test_docker_lifecycle.py -x` | Wave 0 |
| N/A | Generation E2E failure scenarios | unit | `pytest tests/unit/test_generation_e2e.py -x` | Wave 0 |
| N/A | Inference tests consolidated | unit | `pytest tests/unit/test_inference_unit.py -x` | Wave 0 |
| N/A | CI coverage gate enforced | CI | Check `pipeline.yml` for `--cov-fail-under=90` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -q --tb=short`
- **Per wave merge:** `python -m pytest tests/unit/ -v --cov=clod --cov-report=term-missing`
- **Phase gate:** Full suite green with `--cov-fail-under=90`

### Wave 0 Gaps
- [ ] `tests/unit/test_services_slash.py` -- /services command routing tests
- [ ] `tests/unit/test_docker_lifecycle.py` -- _reset_service, _compose_base, profile switch E2E
- [ ] `tests/unit/test_generation_e2e.py` -- generation failure scenarios with file output
- [ ] `tests/unit/test_inference_unit.py` -- consolidated from tests/integration/test_inference.py
- [ ] `.github/workflows/pipeline.yml` -- add `--cov-fail-under=90` to unit-tests job

## Sources

### Primary (HIGH confidence)
- `tests/conftest.py` -- existing fixtures (FakeConsole, mock_cfg, mock_session_state, mock_generation_state)
- `tests/unit/test_startup.py` -- 43 existing startup/service tests, patterns for subprocess mocking
- `tests/unit/test_generation_repl.py` -- existing generation E2E patterns with @patch decorators
- `tests/unit/test_generation_video.py` -- existing video generation and _ensure_generation_service tests
- `tests/unit/test_generation.py` -- existing image generation tests with file output verification
- `tests/integration/test_inference.py` + `tests/integration/conftest.py` -- consolidation target
- `.github/workflows/pipeline.yml` -- CI pipeline structure
- `clod.py` lines 1659-1667 -- `_compose_base` function
- `clod.py` lines 1926-2007 -- `_reset_service` function
- `clod.py` lines 3230-3408 -- `/services` slash command handler

### Secondary (MEDIUM confidence)
- CONTEXT.md decisions -- user locked choices about test boundaries and coverage targets

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies
- Architecture: HIGH -- patterns derived directly from 455 existing tests in the same codebase
- Pitfalls: HIGH -- identified from actual code analysis of existing tests and production code
- Coverage gaps: HIGH -- verified by grepping test files for function references

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable -- testing infrastructure, no external API changes)
