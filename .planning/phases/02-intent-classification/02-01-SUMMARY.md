---
phase: 02-intent-classification
plan: 01
subsystem: nlp
tags: [onnxruntime, tokenizers, intent-classification, embeddings, all-MiniLM-L6-v2]

# Dependency graph
requires:
  - phase: 01-vram-management-offline-gating
    provides: "_get_clod_root() path resolution pattern"
provides:
  - "classify_intent() public API returning (intent, confidence) tuples"
  - "IntentEmbedder class for ONNX-based text embedding"
  - "Pre-computed route centroids for 7 intents (384-dim)"
  - "cosine_similarity() utility for embedding comparison"
  - "build_routes.py script for regenerating centroids"
affects: [02-intent-classification, 03-model-routing, 04-media-generation]

# Tech tracking
tech-stack:
  added: [onnxruntime, tokenizers, numpy]
  patterns: [two-layer-classification, lazy-embedder-init, centroid-routing]

key-files:
  created:
    - intent.py
    - models/intent/build_routes.py
    - models/intent/model_quint8_avx2.onnx
    - models/intent/tokenizer.json
    - models/intent/route_embeddings.npz
    - tests/unit/test_intent.py
  modified:
    - .gitignore

key-decisions:
  - "Lazy-loaded embedder: first classification pays init cost, subsequent calls are instant"
  - "Graceful fallback: embedding layer failure returns keyword result or ('chat', 0.0)"
  - "ONNX model: model_quint8_avx2.onnx (UINT8, AVX2) -- avoids signed INT8 saturation bug on non-VNNI CPUs"
  - "Centroids re-normalized after averaging to maintain valid cosine similarity via dot product"

patterns-established:
  - "Two-layer intent pipeline: keyword fast path then embedding fallback"
  - "ONNX + tokenizers for PyTorch-free embedding inference"
  - "Centroid-based route matching with L2-normalized vectors"
  - "Module-level lazy initialization with _ensure_embedder()"

requirements-completed: [INTENT-01, INTENT-02]

# Metrics
duration: 4min
completed: 2026-03-10
---

# Phase 2 Plan 1: Intent Classification Core Summary

**Two-layer intent classifier (keyword regex + ONNX embedding similarity) classifying into 7 intents under 1ms on CPU using all-MiniLM-L6-v2 quantized model**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-10T17:48:01Z
- **Completed:** 2026-03-10T17:52:31Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Two-layer classification pipeline: keyword/regex rules (sub-1ms) with ONNX embedding fallback (~1ms after warm-up)
- All 7 intents classifiable: chat, code, reason, vision, image_gen, image_edit, video_gen
- 17 unit tests covering keyword matching, embedding path (mocked), cosine similarity, and latency
- Downloaded and deployed all-MiniLM-L6-v2 quantized ONNX model (22MB, UINT8, AVX2)
- Generated L2-normalized route centroids from seed utterances

## Task Commits

Each task was committed atomically:

1. **Task 1: Create intent.py classifier module** - `2d47ad4` (test: RED) + `03e2f09` (feat: GREEN)
2. **Task 2: Download ONNX model files and generate route embeddings** - `91120c3` (feat)

_Note: Task 1 was TDD with separate RED and GREEN commits_

## Files Created/Modified
- `intent.py` - Intent classification module with keyword rules, ONNX embedder, and public API
- `models/intent/build_routes.py` - Script to generate route centroid embeddings from seed utterances
- `models/intent/model_quint8_avx2.onnx` - Quantized UINT8 embedding model (22MB, AVX2 compatible)
- `models/intent/tokenizer.json` - HuggingFace fast tokenizer for all-MiniLM-L6-v2
- `models/intent/route_embeddings.npz` - Pre-computed centroids for 7 intents (7x384, L2-normalized)
- `tests/unit/test_intent.py` - 17 unit tests for keyword, embedding, and similarity layers
- `.gitignore` - Added exclusion for large ONNX binary files

## Decisions Made
- Lazy-loaded embedder to avoid adding startup latency to every REPL session
- Graceful fallback on embedding failure: returns keyword result if available, else ("chat", 0.0)
- Used _get_clod_root() with fallback to __file__.parent for path resolution (avoids hard import dependency on clod.py)
- Centroids re-normalized after mean averaging per Pitfall 7 from research

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test scoping issue with IntentEmbedder import**
- **Found during:** Task 1 (TDD GREEN phase)
- **Issue:** test_low_confidence_returns_below_threshold referenced IntentEmbedder before importing it (import was at end of function)
- **Fix:** Moved IntentEmbedder import to top of test function
- **Files modified:** tests/unit/test_intent.py
- **Verification:** All 17 tests pass
- **Committed in:** 03e2f09 (Task 1 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Minor test fix, no scope creep.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Intent classification module ready for REPL integration (Plan 02-02)
- classify_intent() API available for import by clod.py
- Model files in place for both script and eventual PyInstaller bundling
- /intent slash command patterns documented in research for Plan 02-02

---
*Phase: 02-intent-classification*
*Completed: 2026-03-10*
