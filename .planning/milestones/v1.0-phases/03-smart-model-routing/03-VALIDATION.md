---
phase: 3
slug: smart-model-routing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + coverage |
| **Config file** | none — uses CLI args |
| **Quick run command** | `python -m pytest tests/unit/test_routing.py -x -q` |
| **Full suite command** | `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/test_routing.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | ROUTE-01 | unit | `python -m pytest tests/unit/test_routing.py::test_intent_model_map -x` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | ROUTE-01 | unit | `python -m pytest tests/unit/test_routing.py::test_route_switches_model -x` | ❌ W0 | ⬜ pending |
| 03-01-03 | 01 | 1 | ROUTE-01 | unit | `python -m pytest tests/unit/test_routing.py::test_no_switch_same_model -x` | ❌ W0 | ⬜ pending |
| 03-01-04 | 01 | 1 | ROUTE-01 | unit | `python -m pytest tests/unit/test_routing.py::test_no_switch_low_confidence -x` | ❌ W0 | ⬜ pending |
| 03-01-05 | 01 | 1 | ROUTE-01 | unit | `python -m pytest tests/unit/test_routing.py::test_no_route_disabled -x` | ❌ W0 | ⬜ pending |
| 03-01-06 | 01 | 1 | ROUTE-02 | unit | `python -m pytest tests/unit/test_routing.py::test_confirmation_message -x` | ❌ W0 | ⬜ pending |
| 03-01-07 | 01 | 1 | ROUTE-02 | unit | `python -m pytest tests/unit/test_routing.py::test_no_confirmation_same_model -x` | ❌ W0 | ⬜ pending |
| 03-01-08 | 01 | 1 | ROUTE-03 | unit | `python -m pytest tests/unit/test_routing.py::test_progress_bar_during_pull -x` | ❌ W0 | ⬜ pending |
| 03-01-09 | 01 | 1 | ROUTE-01 | unit | `python -m pytest tests/unit/test_routing.py::test_skip_non_model_intents -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_routing.py` — stubs for ROUTE-01, ROUTE-02, ROUTE-03
- [ ] `tests/conftest.py` update — extend mock_session_state with routing fields if needed

*Existing infrastructure covers conftest.py and pytest setup.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Rich spinner visible during model swap | ROUTE-03 | Visual terminal output | Run clod, trigger intent that requires model switch, observe spinner |
| Rich progress bar during model pull | ROUTE-03 | Visual terminal output + network dependency | Delete a model (`ollama rm`), trigger intent requiring it, observe progress bar |
| Confirmation message auto-proceeds | ROUTE-02 | Timing-dependent terminal interaction | Observe "Switching to X for Y..." message appears briefly before switch |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
