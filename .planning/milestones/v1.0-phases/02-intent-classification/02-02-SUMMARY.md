---
phase: 02-intent-classification
plan: 02
subsystem: nlp
tags: [intent-classification, repl-integration, slash-commands, pyinstaller]

# Dependency graph
requires:
  - phase: 02-intent-classification
    provides: "classify_intent() API, IntentEmbedder, ONNX model files"
provides:
  - "REPL loop intent classification hook (passive, pre-infer)"
  - "/intent slash command (auto, verbose, one-shot, status)"
  - "/model override disabling auto-classification"
  - "PyInstaller bundling for intent model files"
  - "HAS_INTENT graceful import fallback"
affects: [03-model-routing, 04-media-generation]

# Tech tracking
tech-stack:
  added: []
  patterns: [graceful-import-fallback, passive-classification-hook, session-state-intent-fields]

key-files:
  created: []
  modified:
    - clod.py
    - clod.spec
    - tests/unit/test_intent.py
    - tests/conftest.py

key-decisions:
  - "Passive classification: Phase 2 classifies but does not switch models (Phase 3 handles routing)"
  - "HAS_INTENT guard: classify_intent import wrapped in try/except for graceful degradation"
  - "Low confidence threshold at 0.8: below prints dim notice, above is silent"
  - "/model switch disables auto-classification to respect user's explicit choice"

patterns-established:
  - "Session state intent fields: intent_enabled, last_intent, last_confidence, intent_verbose"
  - "Graceful import pattern: try/except with HAS_X flag for optional modules"
  - "Classification hook placement: after message append, before infer() call"

requirements-completed: [INTENT-01, INTENT-03]

# Metrics
duration: 7min
completed: 2026-03-10
---

# Phase 2 Plan 2: REPL Integration Summary

**Intent classification wired into REPL loop with /intent command, /model override, and PyInstaller bundling for ONNX model files**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-10T17:54:43Z
- **Completed:** 2026-03-10T18:01:47Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Every non-slash user input classified before infer() when intent_enabled is True
- /intent command with 4 sub-modes: auto, verbose, one-shot text, status display
- /model switch disables auto-classification with notification; /intent auto re-enables
- PyInstaller spec bundles model_quint8_avx2.onnx, tokenizer.json, route_embeddings.npz
- 8 new tests for slash command integration, all 396 tests pass at 83% coverage

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire intent classification into REPL loop, /intent command, and /model override**
   - `6b146b5` (test: RED -- failing tests for /intent and /model override)
   - `26c9ae4` (feat: GREEN -- implementation passing all tests)
2. **Task 2: Update PyInstaller spec** - `51858f8` (chore)

_Note: Task 1 was TDD with separate RED and GREEN commits_

## Files Created/Modified
- `clod.py` - Import classify_intent, session_state intent fields, REPL classification hook, /intent command, /model override, print_help update
- `clod.spec` - Intent model datas (3 files) and hiddenimports (intent, onnxruntime, tokenizers)
- `tests/unit/test_intent.py` - 8 new tests for slash command integration
- `tests/conftest.py` - mock_session_state fixture updated with intent fields

## Decisions Made
- Passive classification in Phase 2: classifies but doesn't switch models (Phase 3 will handle routing)
- HAS_INTENT flag for graceful degradation if intent module unavailable
- Low confidence threshold at 0.8 prints dim notice; high confidence is silent
- /model disables auto-classification for both cloud and Ollama model switches

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Intent classification fully integrated into REPL loop
- Passive classification provides last_intent and last_confidence in session_state
- Phase 3 (Smart Model Routing) can read session_state intent fields to auto-switch models
- PyInstaller bundling ready for compiled exe distribution

---
*Phase: 02-intent-classification*
*Completed: 2026-03-10*
