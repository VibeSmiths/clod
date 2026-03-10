---
phase: 01-vram-management-offline-gating
plan: 01
subsystem: infra
tags: [vram, ollama, gpu, nvidia-smi, rich-panel, docker-compose]

# Dependency graph
requires: []
provides:
  - "_get_loaded_models: query Ollama /api/ps for loaded models"
  - "_unload_model: keep_alive:0 model unload with retry"
  - "_verify_vram_free: nvidia-smi VRAM check with graceful no-GPU fallback"
  - "_vram_transition_panel: Rich panel showing VRAM usage during transitions"
  - "_ensure_model_ready: user-confirmed model switching with unload/pull/warmup"
  - "_prepare_for_gpu_service: full GPU handoff (unload -> verify -> start -> poll)"
  - "_restore_after_gpu_service: post-generation model reload prompt"
  - "OLLAMA_MAX_LOADED_MODELS=1 in docker-compose.yml"
affects: [media-generation, model-routing, sd-comfyui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "VRAM management via Ollama keep_alive:0 API for explicit model unload"
    - "nvidia-smi polling for VRAM verification with graceful no-GPU fallback"
    - "User confirmation before mid-conversation model switches"
    - "Post-generation prompt before reloading previous model"
    - "Full GPU handoff: unload -> verify VRAM -> docker compose up -> poll health"

key-files:
  created:
    - "tests/unit/test_vram.py"
  modified:
    - "clod.py"

key-decisions:
  - "Retry unload once after 3s wait on failure; do not attempt Ollama restart"
  - "Graceful degradation when nvidia-smi unavailable -- proceed optimistically"
  - "OLLAMA_MAX_LOADED_MODELS defaults to 1 via env var substitution in docker-compose.yml"

patterns-established:
  - "VRAM transition panel: Rich Panel with used/total/free MB and GPU name"
  - "Model ready check: loaded query -> confirm -> unload -> verify VRAM -> load -> verify"
  - "GPU service handoff: save prev model -> unload -> verify -> docker up -> poll health"

requirements-completed: [VRAM-01, VRAM-02, VRAM-03]

# Metrics
duration: 13min
completed: 2026-03-10
---

# Phase 01 Plan 01: VRAM Management Summary

**Safe GPU memory lifecycle with keep_alive:0 unload, nvidia-smi verification, Rich VRAM panels, user-confirmed model switches, and full SD/ComfyUI handoff sequence**

## Performance

- **Duration:** 13 min
- **Started:** 2026-03-10T13:56:49Z
- **Completed:** 2026-03-10T14:10:10Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- 7 VRAM management functions implemented in clod.py with full test coverage (21 tests)
- Full GPU handoff sequence: unload models -> verify VRAM free -> docker compose up -> poll health endpoint
- User confirmation for mid-conversation model switches and post-generation model reload
- OLLAMA_MAX_LOADED_MODELS=1 already configured in docker-compose.yml as safety net

## Task Commits

Each task was committed atomically:

1. **Task 1: VRAM management functions and tests (RED)** - `8d3af8c` (test)
2. **Task 1: VRAM management functions and tests (GREEN)** - `9dadb2e` (feat)

_Task 2 verified existing docker-compose.yml config and full test suite (363 tests pass, no regressions). No additional file changes needed._

## Files Created/Modified
- `clod.py` - Added VRAM Management section with 7 functions after recommend_model_for_vram
- `tests/unit/test_vram.py` - 21 unit tests covering all VRAM management functions

## Decisions Made
- Retry model unload once after 3s wait; warn user on persistent failure (no Ollama restart in this phase)
- When nvidia-smi unavailable, skip VRAM verification and proceed optimistically with dim message
- OLLAMA_MAX_LOADED_MODELS was already configured in docker-compose.yml with env var substitution defaulting to 1

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed FakeConsole Panel text extraction**
- **Found during:** Task 1 (GREEN phase)
- **Issue:** FakeConsole.print stored `str(Panel(...))` which gives repr, not renderable text, causing assertion failures
- **Fix:** Extract Panel.renderable attribute when object has it
- **Files modified:** tests/unit/test_vram.py
- **Verification:** All 21 tests pass
- **Committed in:** 9dadb2e (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Test infrastructure fix necessary for correct assertions. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- VRAM management functions ready for integration with /model command and SD/ComfyUI workflows
- _prepare_for_gpu_service and _restore_after_gpu_service ready to wire into media generation paths
- _ensure_model_ready ready to integrate with model routing in pick_adapter or handle_slash

---
*Phase: 01-vram-management-offline-gating*
*Completed: 2026-03-10*

## Self-Check: PASSED

All files, commits, functions, and docker-compose config verified present.
