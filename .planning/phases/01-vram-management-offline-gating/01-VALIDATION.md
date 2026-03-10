---
phase: 1
slug: vram-management-offline-gating
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + coverage |
| **Config file** | None (pytest invoked via command line) |
| **Quick run command** | `python -m pytest tests/unit/test_vram.py tests/unit/test_offline.py -x -q` |
| **Full suite command** | `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/test_vram.py tests/unit/test_offline.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | VRAM-01 | unit | `python -m pytest tests/unit/test_vram.py::test_env_config -x` | ❌ W0 | ⬜ pending |
| 01-01-02 | 01 | 1 | VRAM-02 | unit | `python -m pytest tests/unit/test_vram.py::test_unload_before_load -x` | ❌ W0 | ⬜ pending |
| 01-01-03 | 01 | 1 | VRAM-03 | unit | `python -m pytest tests/unit/test_vram.py::test_prepare_for_gpu_service -x` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | OFFL-01 | unit | `python -m pytest tests/unit/test_offline.py::test_offline_blocks_cloud -x` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 1 | OFFL-02 | unit | `python -m pytest tests/unit/test_startup.py::test_compute_features_offline -x` | Partial | ⬜ pending |
| 01-02-03 | 02 | 1 | OFFL-03 | unit | `python -m pytest tests/unit/test_offline.py::test_offline_indicator -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_vram.py` — stubs for VRAM-01, VRAM-02, VRAM-03
- [ ] `tests/unit/test_offline.py` — stubs for OFFL-01, OFFL-03
- [ ] Extend `tests/unit/test_startup.py` — OFFL-02 partially covered, needs new tests for extended `_compute_features()`
- [ ] Mock patterns: `responses` library for Ollama API mocking, `monkeypatch` for `query_gpu_vram` subprocess mock

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| VRAM numbers in Rich panel | VRAM-03 | Visual output verification | Run clod, trigger model switch, verify Rich panel shows VRAM before/after |
| Offline indicator in prompt | OFFL-03 | Interactive REPL rendering | Run clod with LiteLLM down, verify prompt shows offline tag |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
