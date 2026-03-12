---
phase: 6
slug: docker-service-integration-testing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=7.4 + pytest-cov >=4.1 |
| **Config file** | pyproject.toml (coverage settings) |
| **Quick run command** | `python -m pytest tests/unit/ -q --tb=short` |
| **Full suite command** | `python -m pytest tests/unit/ -v --cov=clod --cov-report=term-missing --cov-fail-under=90` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -q --tb=short`
- **After every plan wave:** Run `python -m pytest tests/unit/ -v --cov=clod --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | /services start routing | unit | `pytest tests/unit/test_services_slash.py -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | /services stop routing | unit | `pytest tests/unit/test_services_slash.py -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | /services reset routing | unit | `pytest tests/unit/test_services_slash.py -x` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | _reset_service branches | unit | `pytest tests/unit/test_docker_lifecycle.py -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 1 | _compose_base function | unit | `pytest tests/unit/test_docker_lifecycle.py -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 1 | Profile switch E2E | unit | `pytest tests/unit/test_docker_lifecycle.py -x` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 2 | Generation failure scenarios | unit | `pytest tests/unit/test_generation_e2e.py -x` | ❌ W0 | ⬜ pending |
| 06-03-02 | 03 | 2 | File output verification | unit | `pytest tests/unit/test_generation_e2e.py -x` | ❌ W0 | ⬜ pending |
| 06-04-01 | 04 | 2 | test_inference.py consolidation | unit | `pytest tests/unit/test_inference_unit.py -x` | ❌ W0 | ⬜ pending |
| 06-04-02 | 04 | 2 | CI coverage gate | CI | Check `pipeline.yml` for `--cov-fail-under=90` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_services_slash.py` — /services command routing tests
- [ ] `tests/unit/test_docker_lifecycle.py` — _reset_service, _compose_base, profile switch E2E
- [ ] `tests/unit/test_generation_e2e.py` — generation failure scenarios with file output
- [ ] `tests/unit/test_inference_unit.py` — consolidated from tests/integration/test_inference.py

*Existing infrastructure (pytest, responses, FakeConsole, mock_cfg) covers all framework needs.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
