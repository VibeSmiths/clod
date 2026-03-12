---
phase: 01-vram-management-offline-gating
plan: 03
subsystem: gpu
tags: [vram, ollama, nvidia-smi, gpu-lifecycle, slash-commands]

requires:
  - phase: 01-vram-management-offline-gating (plans 01-02)
    provides: "_ensure_model_ready, _prepare_for_gpu_service, _restore_after_gpu_service, _get_loaded_models, _unload_model, _verify_vram_free functions"
provides:
  - "Live VRAM management wiring in /model, /gpu use, /sd handlers"
  - "Safe model transitions with unload-before-load in all user-facing paths"
  - "nvidia-smi VRAM verification before GPU service startup"
  - "Previous model restore offer after /sd stop"
affects: [phase-04-media-generation]

tech-stack:
  added: []
  patterns:
    - "_ensure_model_ready replaces warmup_ollama_model in all slash handlers"
    - "VRAM cleanup (unload + verify) before every sd_switch_mode call"

key-files:
  created: []
  modified:
    - clod.py
    - tests/unit/test_vram.py

key-decisions:
  - "Used lower-level _get_loaded_models/_unload_model/_verify_vram_free in /sd handlers instead of _prepare_for_gpu_service to avoid conflicting with sd_switch_mode docker compose calls"
  - "_verify_vram_free called unconditionally (not only when models were loaded) because VRAM could be consumed by other processes"
  - "VRAM warning on /sd is non-blocking -- proceed with sd_switch_mode regardless but inform user"

patterns-established:
  - "All model switching goes through _ensure_model_ready (never warmup_ollama_model directly)"
  - "GPU service startup always preceded by VRAM unload + nvidia-smi verification"

requirements-completed: [VRAM-02, VRAM-03]

duration: 10min
completed: 2026-03-10
---

# Phase 1 Plan 3: VRAM Wiring Summary

**Wired VRAM management functions into /model, /gpu use, and /sd slash command handlers with unload-before-load, nvidia-smi verification, and post-stop model restore**

## Performance

- **Duration:** 10 min
- **Started:** 2026-03-10T15:06:47Z
- **Completed:** 2026-03-10T15:16:47Z
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- /model for non-cloud models now calls _ensure_model_ready (unload-before-load with user confirmation)
- /gpu use calls _ensure_model_ready with confirm=False (user already explicitly requested)
- /sd image|video|start unloads all loaded Ollama models and verifies VRAM via nvidia-smi before sd_switch_mode
- /sd stop calls _restore_after_gpu_service to offer reloading the previous model
- warmup_ollama_model no longer called directly from any slash handler
- 8 new wiring tests added, all 371 unit tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for VRAM wiring** - `a3bd735` (test)
2. **Task 1 (GREEN): Wire VRAM management into handlers** - `5b29db7` (feat)

_TDD task with RED/GREEN commits_

## Files Created/Modified
- `clod.py` - Replaced warmup_ollama_model calls with _ensure_model_ready in /model and /gpu use; added VRAM cleanup before sd_switch_mode in /sd image|video|start; added _restore_after_gpu_service after /sd stop
- `tests/unit/test_vram.py` - Added 8 tests for handle_slash VRAM wiring (Tests 1-8 covering all handlers)

## Decisions Made
- Used lower-level VRAM functions (_get_loaded_models, _unload_model, _verify_vram_free) instead of _prepare_for_gpu_service in /sd handlers to avoid conflicting with sd_switch_mode's own docker compose operations
- _verify_vram_free called unconditionally before GPU service startup (even when no models were loaded) since other processes could consume VRAM
- VRAM warning is non-blocking -- SD service starts regardless, but user is informed of potential memory issues

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All VRAM management functions are now live in user-facing paths
- Phase 1 gap closure complete -- no more dead code in VRAM management
- Ready for Phase 2 and beyond

## Self-Check: PASSED

- clod.py: FOUND
- tests/unit/test_vram.py: FOUND
- 01-03-SUMMARY.md: FOUND
- Commit a3bd735: FOUND
- Commit 5b29db7: FOUND

---
*Phase: 01-vram-management-offline-gating*
*Completed: 2026-03-10*
