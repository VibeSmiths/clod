# Phase 6: Docker Service Integration & Testing - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

End-to-end integration tests covering the full Docker service lifecycle: start/stop/reset, health checks, config restoration, env wizard, and generation pipeline against mocked services. Targets 90%+ test coverage with CI enforcement. Consolidates mock-based integration tests into tests/unit/.

</domain>

<decisions>
## Implementation Decisions

### Test Boundaries
- All tests fully mocked — no Docker Desktop required. HTTP mocking via `responses` library, subprocess mocking via `monkeypatch`
- Docker CLI commands (docker compose up, docker ps) mocked at subprocess level — patch `subprocess.run` to return fake docker output
- Tests go in `tests/unit/` alongside existing unit tests — since everything is mocked, they're effectively unit tests
- Target: 90%+ test coverage (currently ~85% with 455 tests)

### Service Lifecycle Coverage
- Test ALL Docker service operations: `_check_service_health`, `_offer_docker_startup`, `_compose_base`, `/services start|stop|reset`, `_get_service_volumes`, `_reset_service`, `_setup_env_wizard`, `_ensure_local_configs`
- Test both layers: handle_slash('/services ...') for command parsing/routing AND underlying functions directly for logic
- `_setup_env_wizard`: mock all console.input() prompts — test happy path (user provides key), skip path (enter), and .env.example missing path
- `_ensure_local_configs`: test local bundled restore path only — skip GitHub fallback HTTP testing

### Generation Pipeline Integration
- Full flow E2E tests for `_handle_generation_intent`: intent → VRAM handoff → craft prompt → generate → save → restore, with all dependencies mocked
- Verify actual file output — write fake PNG/video bytes, assert file appears at expected path with `clod_{timestamp}_{hash}.ext` naming, using `tmp_path` fixture
- Dedicated E2E test for Docker profile switch flow: detect wrong profile → confirm → stop current → verify VRAM → start new → poll health
- Test key failure scenarios: service unreachable during generation, VRAM verification timeout, docker compose failure — verify graceful degradation and error messages

### CI Compatibility
- No special handling needed — fully mocked tests run in existing `python -m pytest tests/unit/` CI step
- Add `--cov-fail-under=90` to CI pipeline to enforce coverage threshold
- Consolidate `tests/integration/test_inference.py` into `tests/unit/` (it uses HTTP mocks, not real services). Keep `test_exe.py` separate (needs compiled binary)
- Update `.github/workflows/pipeline.yml`: add coverage gate, adjust integration-tests job to only run exe tests

### Claude's Discretion
- Exact test file organization within tests/unit/ (how many test files, naming)
- Which specific failure scenarios to E2E test (pick 3-4 most impactful)
- How to consolidate test_inference.py (merge into existing test file or rename)
- Mock fixture design for subprocess.run Docker commands

</decisions>

<specifics>
## Specific Ideas

- Follow the existing `responses` library pattern used throughout tests/unit/ for HTTP mocking
- Use `FakeConsole` from conftest.py for Rich output suppression in tests
- Existing `mock_generation_state` fixture from Phase 4 can be reused for E2E generation tests
- `tmp_path` pytest fixture for file output verification — automatic cleanup

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `FakeConsole` (tests/conftest.py): Rich console mock with Progress/Live support — reuse for all service tests
- `mock_generation_state` (tests/conftest.py): Session state fixture with generation fields — reuse for E2E gen tests
- `responses` library: HTTP mock pattern used in 20+ existing test files — same pattern for service health mocks
- `mock_cfg` (tests/conftest.py): Config fixture with all service URLs — extend for compose_file path

### Established Patterns
- `@responses.activate` decorator for HTTP mocking
- `monkeypatch.setattr()` for subprocess and function patching
- Section-grouped test files: `test_startup.py` (22 tests), `test_generation.py` (20 tests), etc.
- Test naming: `test_{function}_{scenario}` convention

### Integration Points
- `_check_service_health` (clod.py:1602): HTTP GET to each service — mock with `responses`
- `_offer_docker_startup` (clod.py:1669): subprocess.run for docker compose + polling — mock both
- `_reset_service` (clod.py:1926): subprocess + file I/O — mock subprocess, use tmp_path for files
- `handle_slash` (clod.py:3230): `/services` command tree — test via handle_slash() calls
- `_handle_generation_intent` (clod.py:~1248): Full generation orchestrator — mock all downstream calls
- `.github/workflows/pipeline.yml`: CI pipeline — add --cov-fail-under=90

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-docker-service-integration-testing*
*Context gathered: 2026-03-10*
