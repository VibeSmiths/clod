---
phase: 04-media-generation-pipeline
plan: 02
subsystem: generation
tags: [comfyui, video, docker, ollama, prompt-crafting]

requires:
  - phase: 01-vram-management-offline-gating
    provides: _prepare_for_gpu_service, _verify_vram_free, _unload_model, warmup_ollama_model
  - phase: 04-media-generation-pipeline plan 01
    provides: _save_generation_output, _generate_image, _craft_sd_prompt
provides:
  - _craft_video_prompt (ComfyUI-optimized prompt via llama3.1:8b)
  - _build_video_workflow (parameterized ComfyUI workflow JSON)
  - _download_comfyui_output (download from ComfyUI /view endpoint)
  - _generate_video (queue + poll ComfyUI API)
  - _ensure_generation_service (auto-detect and start/switch docker profiles)
  - _silent_restore_model (auto-reload previous Ollama model without prompting)
  - VIDEO_PROMPT_SYSTEM constant
affects: [04-media-generation-pipeline plan 03]

tech-stack:
  added: []
  patterns: [comfyui-queue-poll, profile-switch-with-confirmation, silent-model-restore]

key-files:
  created: [tests/unit/test_generation_video.py]
  modified: [clod.py]

key-decisions:
  - "Reuse _save_generation_output from Plan 01 for ComfyUI file downloads"
  - "Ship basic workflow template with note to customize per installed video model"
  - "_silent_restore_model is a separate function from _restore_after_gpu_service (per Pitfall 7)"

patterns-established:
  - "ComfyUI queue+poll: POST /prompt, poll GET /history/{id}, download via /view"
  - "Profile switch confirmation: warn message + y/N input before sd_switch_mode"
  - "Silent model restore: auto-reload without confirmation prompt"

requirements-completed: [VID-01, VID-02, VID-03, DOCK-01, DOCK-02, DOCK-03]

duration: 18min
completed: 2026-03-10
---

# Phase 4 Plan 02: Video Generation & Docker Orchestration Summary

**ComfyUI video generation via queue+poll API with auto-detect docker profile switching and silent model restore**

## Performance

- **Duration:** 18 min
- **Started:** 2026-03-10T23:57:54Z
- **Completed:** 2026-03-11T00:15:32Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Video prompt crafting via llama3.1:8b with VIDEO_PROMPT_SYSTEM constant
- ComfyUI integration using POST /prompt queue + GET /history poll pattern with 10-min timeout
- Docker profile orchestration: auto-detect running services, confirm before switch, delegate GPU verification
- Silent model restore function that auto-reloads without user prompt (separate from existing _restore_after_gpu_service)
- 14 unit tests covering all new functions, 443 total tests passing with 84% coverage

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for video generation** - `b7e2c18` (test)
2. **Task 1 (GREEN): Implement video generation functions** - `27cb089` (feat)
3. **Task 2: Full test suite regression check** - no code changes, 443 tests pass

## Files Created/Modified
- `clod.py` - Added VIDEO_PROMPT_SYSTEM constant, _craft_video_prompt, _build_video_workflow, _download_comfyui_output, _generate_video, _ensure_generation_service, _silent_restore_model
- `tests/unit/test_generation_video.py` - 14 unit tests for all new video generation and docker orchestration functions

## Decisions Made
- Reused `_save_generation_output` from Plan 01 inside `_download_comfyui_output` instead of duplicating file-save logic
- Shipped a basic ComfyUI workflow template (KSampler + VHS_VideoCombine nodes) with documentation noting it should be customized per installed video model
- Created `_silent_restore_model` as a completely separate function from `_restore_after_gpu_service`, not modifying the existing function (per Pitfall 7)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Video generation pipeline ready for Plan 03 REPL integration
- _ensure_generation_service handles both image and video intent routing
- _silent_restore_model available for post-generation model reload

## Self-Check: PASSED

- All files exist (test file, SUMMARY.md)
- All commits verified (b7e2c18, 27cb089)
- All 6 functions present in clod module

---
*Phase: 04-media-generation-pipeline*
*Completed: 2026-03-10*
