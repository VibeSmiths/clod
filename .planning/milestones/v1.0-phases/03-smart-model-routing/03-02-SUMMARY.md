---
phase: 03-smart-model-routing
plan: 02
subsystem: ui
tags: [rich, progress-bar, ollama, model-pull, spinner]

# Dependency graph
requires:
  - phase: 01-vram-management-offline-gating
    provides: ollama_pull function and model management infrastructure
provides:
  - Rich Progress bar in ollama_pull with download size, speed, and ETA
  - Verified spinner in warmup_ollama_model
affects: [04-media-generation]

# Tech tracking
tech-stack:
  added: [rich.progress.Progress, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn]
  patterns: [Rich Progress context manager for streaming download display]

key-files:
  created: []
  modified: [clod.py, tests/unit/test_routing.py, tests/conftest.py]

key-decisions:
  - "FakeConsole wraps real rich.console.Console for full Progress/Live compatibility in tests"

patterns-established:
  - "Rich Progress with console= param for testable progress displays"
  - "FakeConsole delegates to real Console for internal Rich component compatibility"

requirements-completed: [ROUTE-03]

# Metrics
duration: 17min
completed: 2026-03-10
---

# Phase 3 Plan 02: Rich Progress Bar Summary

**Rich Progress bar with download size, speed, and ETA in ollama_pull; existing spinner verified for warmup**

## Performance

- **Duration:** 17 min
- **Started:** 2026-03-10T19:22:03Z
- **Completed:** 2026-03-10T19:39:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Replaced ASCII `#` progress bar in ollama_pull with Rich Progress bar showing percentage, download size, transfer speed, and ETA
- Added 3 new tests: progress bar during pull, non-download phases, spinner during warmup
- Updated FakeConsole test fixture to support Rich Progress/Live components

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Add failing tests** - `119052c` (test)
2. **Task 1 GREEN: Implement Rich Progress bar** - `aa5636b` (feat)
3. **Task 2: Fix existing tests and full validation** - `cba34a9` (fix)

_Note: TDD task had RED/GREEN commits. No refactor phase needed._

## Files Created/Modified
- `clod.py` - Added rich.progress imports; replaced ASCII bar loop with Progress context manager in ollama_pull
- `tests/unit/test_routing.py` - Added test_progress_bar_during_pull, test_pull_non_download_phases, test_spinner_during_warmup
- `tests/conftest.py` - Updated _FakeConsole to wrap real rich.console.Console for Progress compatibility

## Decisions Made
- FakeConsole now wraps a real `rich.console.Console(file=StringIO())` instead of being a minimal stub, because `rich.progress.Progress` needs internal Console attributes (`get_time`, `_live_stack`, context manager protocol). This avoids constantly chasing missing attributes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FakeConsole incompatible with Rich Progress**
- **Found during:** Task 2 (full suite validation)
- **Issue:** Rich Progress constructor accesses `console.get_time`, `console.log`, `console._live_stack`, and uses console as context manager -- all missing from the minimal FakeConsole stub
- **Fix:** Rewrote FakeConsole to wrap a real `rich.console.Console(file=StringIO())`, delegating unoverridden attributes via `__getattr__` and explicit `__enter__`/`__exit__`
- **Files modified:** tests/conftest.py
- **Verification:** All 409 tests pass
- **Committed in:** cba34a9

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Fix was necessary for correctness. No scope creep.

## Issues Encountered
None beyond the FakeConsole compatibility fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Rich Progress bar ready for production model pulls
- Spinner already verified in warmup_ollama_model
- Full test suite green (409 passed)

---
*Phase: 03-smart-model-routing*
*Completed: 2026-03-10*
