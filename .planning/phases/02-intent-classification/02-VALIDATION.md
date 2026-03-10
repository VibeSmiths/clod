---
phase: 2
slug: intent-classification
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + coverage |
| **Config file** | none — uses CLI args |
| **Quick run command** | `python -m pytest tests/unit/test_intent.py -x -q` |
| **Full suite command** | `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/test_intent.py -x -q`
- **After every plan wave:** Run `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | INTENT-01 | unit | `python -m pytest tests/unit/test_intent.py::test_classify_all_intents -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | INTENT-01 | unit | `python -m pytest tests/unit/test_intent.py::test_keyword_classification -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | INTENT-01 | unit | `python -m pytest tests/unit/test_intent.py::test_embedding_classification -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | INTENT-02 | unit | `python -m pytest tests/unit/test_intent.py::test_classification_latency -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 1 | INTENT-03 | unit | `python -m pytest tests/unit/test_intent.py::test_model_override_disables_intent -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 1 | INTENT-03 | unit | `python -m pytest tests/unit/test_intent.py::test_intent_auto_reenables -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_intent.py` — stubs for INTENT-01, INTENT-02, INTENT-03
- [ ] Mock/fixture for ONNX session — avoid requiring real model files in CI
- [ ] `pip install onnxruntime tokenizers` — new dependencies

*Existing infrastructure covers conftest.py and pytest setup.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cold start latency acceptable | INTENT-02 | Requires real ONNX model load timing | Run `clod.exe`, time first classification vs subsequent |
| Model switch notification UX | INTENT-01 | Visual verification of Rich output | Verify intent notification only shows on model switch |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
