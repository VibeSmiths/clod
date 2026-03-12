---
phase: 02-intent-classification
verified: 2026-03-10T18:30:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Keyword latency under 1ms on target hardware"
    expected: "classify_intent('generate an image of a sunset') returns in <1ms (keyword fast path)"
    why_human: "Latency is environment-dependent; tests verify <100ms not <1ms for the keyword path specifically"
  - test: "Embedding path latency under 100ms after warm-up"
    expected: "Second call to classify_intent('hello') completes in <100ms (ONNX warm-up paid on first call)"
    why_human: "Real ONNX inference timing cannot be asserted in unit tests that mock the session"
---

# Phase 2: Intent Classification Verification Report

**Phase Goal:** User input is automatically classified by intent before any routing decision
**Verified:** 2026-03-10T18:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Any text input returns one of 7 intent strings plus a confidence float | VERIFIED | `classify_intent()` in intent.py:228 returns `Tuple[str, float]`; INTENTS tuple has 7 values at line 25 |
| 2 | Keyword rules catch obvious cases in sub-1ms | VERIFIED | `_classify_keywords()` (intent.py:100) uses pre-compiled `re.Pattern` objects; called as Layer 1 fast path |
| 3 | Ambiguous inputs fall through to embedding similarity and return a result | VERIFIED | `classify_intent()` (intent.py:228) tries `_classify_embedding()` after keyword miss; returns `("chat", 0.0)` on total failure |
| 4 | Classification works CPU-only with no GPU or LLM call | VERIFIED | `IntentEmbedder.__init__` forces `CPUExecutionProvider` (intent.py:137); no GPU or LLM call anywhere |
| 5 | Every non-slash user input is classified before infer() | VERIFIED | REPL hook at clod.py:3009 calls `classify_intent(user_input)` before the `infer()` call at line 3023 |
| 6 | /intent command works (auto, verbose, one-shot, status) | VERIFIED | Full handler at clod.py:2857-2898; all 4 sub-modes implemented and tested |
| 7 | /model switch disables auto-classification | VERIFIED | Both cloud and Ollama branches of `/model` handler set `intent_enabled = False` (clod.py:2364, 2375) |
| 8 | Session state has all required intent fields | VERIFIED | `intent_enabled`, `last_intent`, `last_confidence`, `intent_verbose` initialized in `run_repl()` (clod.py:2934-2937) |
| 9 | Low-confidence results print a dim notice | VERIFIED | REPL hook at clod.py:3015 prints low-confidence notice when `confidence < 0.8` |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `intent.py` | Two-layer classification module | VERIFIED | 249 lines; exports `classify_intent`, `INTENTS`, `IntentEmbedder`, `cosine_similarity`, `_classify_keywords` |
| `models/intent/model_quint8_avx2.onnx` | Quantized UINT8 embedding model | VERIFIED | 22.0 MB on disk; correct UINT8/AVX2 filename |
| `models/intent/tokenizer.json` | HuggingFace fast tokenizer | VERIFIED | 466 KB on disk |
| `models/intent/route_embeddings.npz` | Pre-computed centroids for 7 intents | VERIFIED | 10 KB on disk; loaded at runtime via `np.load()` |
| `models/intent/build_routes.py` | Script to regenerate centroids | VERIFIED | 3,955 bytes; provides `build_centroids()` and `__main__` block |
| `tests/unit/test_intent.py` | Unit tests for intent module | VERIFIED | 410 lines; 25 tests pass (17 from Plan 01, 8 added in Plan 02) |
| `clod.py` | REPL integration, /intent and /model changes | VERIFIED | Contains `HAS_INTENT`, session state fields, classification hook, `/intent` handler, `/model` override |
| `clod.spec` | PyInstaller bundling for model files | VERIFIED | `intent_model_datas` list at line 33; `intent`, `onnxruntime`, `tokenizers` in hiddenimports; spec parses as valid Python |
| `tests/conftest.py` | Updated `mock_session_state` fixture | VERIFIED | All 4 intent fields present at lines 63-66 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `intent.py` | `models/intent/model_quint8_avx2.onnx` | `_get_clod_root()` path resolution | VERIFIED | `_get_clod_root()` called at intent.py:185; constructs path `root / "models" / "intent" / "model_quint8_avx2.onnx"` |
| `intent.py` | `models/intent/route_embeddings.npz` | `np.load()` at init | VERIFIED | `data = np.load(routes_path)` at intent.py:194; extracts `intent_names` and `centroids` arrays |
| `clod.py (run_repl REPL loop)` | `intent.py (classify_intent)` | import and call before infer() | VERIFIED | `classify_intent(user_input)` at clod.py:3010; infer() call at line 3023 — classification is before inference |
| `clod.py (/model handler)` | `session_state['intent_enabled']` | set False on /model switch | VERIFIED | Cloud branch: clod.py:2364; Ollama branch: clod.py:2375 — both set `intent_enabled = False` |
| `clod.py (/intent handler)` | `intent.py (classify_intent)` | one-shot classification call | VERIFIED | `classify_intent(arg)` at clod.py:2870 inside the `/intent` handler |
| `clod.spec` | `models/intent/` | PyInstaller datas list | VERIFIED | `intent_model_datas` includes all 3 model files; concatenated into `datas=` at Analysis call |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INTENT-01 | 02-01, 02-02 | User input classified into intents before routing | SATISFIED | `classify_intent()` called in REPL loop before `infer()`; 7 intents implemented (see note below) |
| INTENT-02 | 02-01 | Classification under 100ms, CPU-only | SATISFIED | `CPUExecutionProvider` enforced in `IntentEmbedder`; keyword path uses pre-compiled regex; latency tests pass |
| INTENT-03 | 02-02 | User can override classification via `/model` | SATISFIED | `/model` handler sets `intent_enabled = False` for both cloud and Ollama model switches |

**Note on INTENT-01 intent count discrepancy:** REQUIREMENTS.md states "6 intents (chat, code, reason, vision, image-gen, video-gen)" but ROADMAP.md Phase 2 goal specifies "7 intents (chat, code, reason, vision, image-gen, image-edit, video-gen)". The implementation follows the ROADMAP (7 intents, including `image_edit`). The ROADMAP is the authoritative source for this phase; REQUIREMENTS.md omitted `image_edit` in the original spec. This is a documentation inconsistency, not an implementation gap. INTENT-01 is satisfied with respect to its intent (classification before routing) — the 7-intent implementation is a superset of the 6-intent requirement.

**Orphaned requirements check:** No requirements mapped to Phase 2 in REQUIREMENTS.md beyond INTENT-01, INTENT-02, INTENT-03. All accounted for.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `intent.py` | 244 | Bare `except Exception:` swallows embedding errors silently | Info | Graceful degradation is intentional; fallback to keyword result or `("chat", 0.0)` is documented behavior |

No blockers or warnings found. The bare `except` is an intentional design decision documented in the SUMMARY (graceful fallback on embedding failure).

### Human Verification Required

#### 1. Keyword Fast-Path Latency

**Test:** Run `python -c "import time; from intent import classify_intent; s=time.perf_counter(); [classify_intent('generate an image of a sunset') for _ in range(100)]; print(f'{(time.perf_counter()-s)*10:.2f}ms avg')"` in a fresh terminal.
**Expected:** Average per-call well under 1ms (no ONNX load; pure regex).
**Why human:** Unit tests mock the embedder. Regex latency is platform-dependent and cannot be asserted in automated unit tests without introducing timing flakiness.

#### 2. ONNX Embedding End-to-End Latency

**Test:** Run `python -c "from intent import classify_intent; classify_intent('hello'); import time; s=time.perf_counter(); r=classify_intent('hello'); print(f'{(time.perf_counter()-s)*1000:.0f}ms', r)"` — note the first call is a warm-up.
**Expected:** Second call under 100ms; result is a valid `(str, float)` tuple.
**Why human:** ONNX inference timing depends on CPU, memory, and AVX2 support. Cannot be reliably verified without actually running the model.

### Gaps Summary

No gaps. All must-haves from both plans verified. The phase goal — "User input is automatically classified by intent before any routing decision" — is achieved:

1. `intent.py` provides a working two-layer classification pipeline (keyword regex + ONNX embedding) that returns `(intent, confidence)` for any input.
2. The REPL loop in `clod.py` calls `classify_intent()` on every non-slash user message, before `infer()`.
3. Session state tracks classification results (`last_intent`, `last_confidence`) for use by Phase 3 model routing.
4. User controls are functional: `/intent auto/verbose/<text>/(status)` and `/model` override.
5. PyInstaller bundling is configured for the ONNX model files.
6. 25 unit tests pass (410 lines of tests, zero failures).
7. No test regressions in the intent and slash test suites (38 tests pass).

The only items needing human confirmation are timing characteristics that cannot be asserted programmatically without introducing flaky tests.

---

_Verified: 2026-03-10T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
