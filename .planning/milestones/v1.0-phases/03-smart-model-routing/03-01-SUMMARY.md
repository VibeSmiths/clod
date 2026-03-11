---
phase: 03-smart-model-routing
plan: 01
subsystem: model-routing
tags: [intent, routing, ollama, model-switching, repl]

requires:
  - phase: 02-intent-classification
    provides: classify_intent() function and HAS_INTENT guard
provides:
  - INTENT_MODEL_MAP dict mapping 7 intents to Ollama models or None
  - _route_to_model() function for automatic model switching
  - Active routing wired into REPL loop after classification
affects: [03-smart-model-routing, 04-media-generation]

tech-stack:
  added: []
  patterns: [intent-to-model mapping dict, guard-based routing with early returns]

key-files:
  created: [tests/unit/test_routing.py]
  modified: [clod.py]

key-decisions:
  - "Routing only fires when confidence >= 0.8 (double-gated: REPL check + function guard)"
  - "Cloud models exempt from auto-routing to respect explicit user choice"
  - "Non-model intents (image_gen/image_edit/video_gen) return True for Phase 4 handling"
  - "_ensure_model_ready called with confirm=False for seamless auto-switching"

patterns-established:
  - "Guard-chain pattern: early-return for disabled/low-confidence/same-model/cloud/non-model before action"

requirements-completed: [ROUTE-01, ROUTE-02]

duration: 9min
completed: 2026-03-10
---

# Phase 3 Plan 1: Smart Model Routing Summary

**INTENT_MODEL_MAP with _route_to_model() auto-switching models based on classified intent, wired into REPL loop**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-10T19:21:57Z
- **Completed:** 2026-03-10T19:30:33Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- INTENT_MODEL_MAP maps all 7 intents to correct Ollama models (4 models) or None (3 Phase 4 intents)
- _route_to_model() handles all edge cases: low confidence, same model, disabled, cloud models, non-model intents, switch failure
- REPL loop actively routes after intent classification (Phase 2 passive comment replaced)
- 10 dedicated routing tests all pass; full suite 405 pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Failing tests for routing** - `f6e53a0` (test)
2. **Task 1 (GREEN): INTENT_MODEL_MAP and _route_to_model()** - `99413e6` (feat)
3. **Task 2: Wire _route_to_model into REPL loop** - `aa5636b` (feat, included in subsequent commit)

_Note: Task 2 REPL wiring was captured in the next commit due to git staging order._

## Files Created/Modified
- `clod.py` - Added INTENT_MODEL_MAP dict (7 entries) and _route_to_model() function; wired routing into REPL loop
- `tests/unit/test_routing.py` - 10 unit tests covering all routing edge cases

## Decisions Made
- Routing only fires when confidence >= 0.8, double-gated at REPL level and inside _route_to_model
- Cloud models (claude-, gpt-, etc.) exempt from auto-routing to respect user's explicit /model choice
- Non-model intents (image_gen, image_edit, video_gen) mapped to None, return True for future Phase 4 handling
- _ensure_model_ready called with confirm=False for seamless background switching
- "Switching to X for Y..." message printed in cyan before each switch for user awareness

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- 4 pre-existing test failures in test_coverage_gaps.py (FakeConsole missing get_time attribute) -- unrelated to routing changes, not addressed per scope boundary rules.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Smart model routing active and tested
- Ready for Plan 03-02 (manual override, /auto command, or additional routing refinements)
- Phase 4 (media generation) can build on None-mapped intents

---
*Phase: 03-smart-model-routing*
*Completed: 2026-03-10*

## Self-Check: PASSED
