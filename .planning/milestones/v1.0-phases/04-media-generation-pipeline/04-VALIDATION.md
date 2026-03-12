---
phase: 4
slug: media-generation-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + coverage |
| **Config file** | tests/conftest.py |
| **Quick run command** | `python -m pytest tests/unit/ -q -x --cov=clod` |
| **Full suite command** | `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/unit/ -q -x --cov=clod`
- **After every plan wave:** Run `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 0 | IMG-01, VID-01 | unit | `python -m pytest tests/unit/test_generation.py -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | IMG-02 | unit | `python -m pytest tests/unit/test_generation.py::test_craft_sd_prompt -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | IMG-03 | unit | `python -m pytest tests/unit/test_generation.py::test_negative_prompts_by_model_type -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | IMG-04, DOCK-01 | unit | `python -m pytest tests/unit/test_generation.py::test_offer_start_image_service -x` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | VID-02 | unit | `python -m pytest tests/unit/test_generation.py::test_craft_video_prompt -x` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 2 | VID-03, DOCK-02, DOCK-03 | unit | `python -m pytest tests/unit/test_generation.py::test_offer_profile_switch_for_video -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_generation.py` — stubs for IMG-01 through VID-03, DOCK-01, DOCK-02
- [ ] Extend `tests/conftest.py` with `mock_generation_state` fixture
- [ ] Mock patterns for `requests.post` to A1111 and ComfyUI endpoints (using `responses` library)

*Existing infrastructure covers DOCK-03 partially (test_vram.py).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Image displays in default viewer | IMG-01 | os.startfile opens OS viewer | Generate an image, verify it opens automatically |
| Video plays in default viewer | VID-01 | os.startfile opens OS viewer | Generate a video, verify it opens automatically |
| Rich progress bar renders correctly | IMG-01 | Visual verification | Watch progress bar during generation, verify smooth updates |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
