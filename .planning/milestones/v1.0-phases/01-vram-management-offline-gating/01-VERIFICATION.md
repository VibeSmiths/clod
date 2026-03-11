---
phase: 01-vram-management-offline-gating
verified: 2026-03-10T16:00:00Z
status: passed
score: 4/4 success criteria verified
re_verification:
  previous_status: gaps_found
  previous_score: 2/4
  gaps_closed:
    - "Only one Ollama model is loaded at a time -- loading a second model automatically unloads the first"
    - "Before launching SD or ComfyUI, the active Ollama model is unloaded and VRAM is verified free"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Mid-conversation model switch confirmation"
    expected: "User sees a confirmation prompt before the model switch proceeds, current model is unloaded first, VRAM panel appears"
    why_human: "Requires live Ollama instance and interactive REPL session"
  - test: "SD/ComfyUI launch with loaded Ollama model"
    expected: "Ollama model is unloaded, VRAM is verified free via nvidia-smi, SD/ComfyUI starts, user is prompted to reload model after /sd stop"
    why_human: "Requires running Docker GPU services and physical GPU"
---

# Phase 01: VRAM Management & Offline Gating Verification Report

**Phase Goal:** Clod safely manages GPU memory across model loads and generation services, and clearly gates features based on connectivity
**Verified:** 2026-03-10T16:00:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure via plan 01-03 (commits a3bd735 and 5b29db7)

## Goal Achievement

### Observable Truths (from Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Only one Ollama model is loaded at a time — loading a second model automatically unloads the first | VERIFIED | `/model` handler at line 2355 calls `_ensure_model_ready(arg, ..., confirm=True)` which unloads all loaded models before loading the new one. `warmup_ollama_model` is no longer called directly from any slash handler. |
| 2 | Before launching SD or ComfyUI, the active Ollama model is unloaded and VRAM is verified free | VERIFIED | `/sd image|video` handler (lines 2537-2551) and `/sd start` handler (lines 2609-2623) both call `_get_loaded_models` + `_unload_model` loop + `_vram_transition_panel`, then unconditionally call `_verify_vram_free()` before `sd_switch_mode`. `/sd stop` calls `_restore_after_gpu_service` at line 2601. |
| 3 | When offline, no outbound HTTP requests are made to cloud LLMs, web search, or external APIs | VERIFIED | `_enforce_offline` called in `infer()` at line 2252 blocks cloud model calls and falls back to local. `execute_tool` checks `web_search_enabled` flag before making SearXNG requests. |
| 4 | The UI shows a clear offline indicator when cloud features are unavailable | VERIFIED | `print_header` at line 2117 accepts `web_search` param and displays `[bold red]OFFLINE[/bold red]` or `[dim]online[/dim]` plus `search: on/off`. Called at line 2843 with `web_search=features.get("web_search_enabled", True)`. |

**Score:** 4/4 success criteria verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `clod.py` (VRAM functions) | `_get_loaded_models`, `_unload_model`, `_verify_vram_free`, `_vram_transition_panel`, `_ensure_model_ready`, `_prepare_for_gpu_service`, `_restore_after_gpu_service` | VERIFIED | All 7 functions exist (lines 549-753), substantive implementations. `_ensure_model_ready` now called from `/model` (line 2355) and `/gpu use` (line 2512). Lower-level VRAM functions called from `/sd` handlers. `_restore_after_gpu_service` called from `/sd stop` (line 2601). |
| `clod.py` (offline functions) | `_is_cloud_request`, `_enforce_offline`, `/search` command, `web_search_enabled` in `_compute_features` | VERIFIED | All exist and are wired as in initial verification. No regressions. |
| `tests/unit/test_vram.py` | 21 original + 8 new wiring tests, all passing | VERIFIED | 29 tests pass in 6.06s. 8 new tests (lines added by plan 01-03) cover `/model`, `/gpu use`, `/sd image|video|start|stop` handler wiring. |
| `tests/unit/test_offline.py` | 12 unit tests | VERIFIED | Passes as part of full suite (371 passed, 0 failures). |
| `tests/unit/test_startup.py` | Extended with `web_search_enabled` tests | VERIFIED | No regressions in full suite run. |
| `docker-compose.yml` | `OLLAMA_MAX_LOADED_MODELS=1` | VERIFIED | Line 293: `- OLLAMA_MAX_LOADED_MODELS=${OLLAMA_MAX_LOADED_MODELS:-1}` unchanged. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `clod.py::handle_slash /model` | `clod.py::_ensure_model_ready` | direct call replacing `warmup_ollama_model` | WIRED | Line 2355: `ok = _ensure_model_ready(arg, session_state["cfg"], console, session_state, confirm=True)` |
| `clod.py::handle_slash /gpu use` | `clod.py::_ensure_model_ready` | direct call with `confirm=False` | WIRED | Line 2512: `ok = _ensure_model_ready(rec, session_state["cfg"], console, session_state, confirm=False)` |
| `clod.py::handle_slash /sd image|video` | `clod.py::_unload_model` | VRAM cleanup before `sd_switch_mode` | WIRED | Lines 2538-2544: `_get_loaded_models` loop calls `_unload_model` for each loaded model before calling `sd_switch_mode` |
| `clod.py::handle_slash /sd image|video` | `clod.py::_verify_vram_free` | nvidia-smi check after unloading | WIRED | Line 2547: `if not _verify_vram_free():` — unconditional call, non-blocking warning |
| `clod.py::handle_slash /sd start` | `clod.py::_verify_vram_free` | nvidia-smi check after unloading | WIRED | Line 2619: `if not _verify_vram_free():` — same pattern as image|video path |
| `clod.py::handle_slash /sd stop` | `clod.py::_restore_after_gpu_service` | restore prompt after stopping SD services | WIRED | Line 2601: `_restore_after_gpu_service(session_state["cfg"], console, session_state)` inside success path |
| `clod.py::infer` | `clod.py::_enforce_offline` | guards cloud calls when offline | WIRED | Unchanged from initial verification — no regression |
| `clod.py::_compute_features` | `clod.py::run_repl session_state` | `web_search_enabled` flag flows to session state | WIRED | Unchanged from initial verification — no regression |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| VRAM-01 | 01-01-PLAN | Ollama configured with OLLAMA_MAX_LOADED_MODELS=1 | SATISFIED | `docker-compose.yml` line 293 sets env var with default of 1 |
| VRAM-02 | 01-01-PLAN + 01-03-PLAN | Before loading a new model, clod explicitly unloads current model using keep_alive:0 | SATISFIED | `_ensure_model_ready` (which calls `_unload_model` with keep_alive:0) is now invoked from both `/model` and `/gpu use` handlers. `warmup_ollama_model` no longer appears in any slash handler. |
| VRAM-03 | 01-01-PLAN + 01-03-PLAN | Before switching to SD/ComfyUI, clod unloads active Ollama model to free GPU VRAM | SATISFIED | `/sd image|video` and `/sd start` handlers call `_get_loaded_models` + `_unload_model` + `_verify_vram_free` before any `sd_switch_mode` call. |
| OFFL-01 | 01-02-PLAN | When in offline mode, all outbound HTTP requests are blocked | SATISFIED | `_enforce_offline` in `infer()` blocks cloud LLM calls; `execute_tool` gates `web_search` on `web_search_enabled`; offline mode sets `pipeline=None` |
| OFFL-02 | 01-02-PLAN | Offline mode auto-detected from service health and can be manually toggled | SATISFIED | `_compute_features` sets `offline_default` based on LiteLLM health + API key; `/offline` command at line 2408 toggles manually |
| OFFL-03 | 01-02-PLAN | UI clearly indicates when offline mode is active | SATISFIED | `print_header` at line 2127-2128 shows `[bold red]OFFLINE[/bold red]` and `search: on/off` indicators |

**Orphaned requirements check:** All 6 phase requirements (VRAM-01 through VRAM-03, OFFL-01 through OFFL-03) are claimed in plan frontmatter and present in REQUIREMENTS.md (lines 24-26, 57-59). VRAM-01/02/03 are marked `[x]` (complete). OFFL-01/02/03 are marked `[x]` (complete). No orphaned requirements.

### Anti-Patterns Found

No anti-patterns detected. Grep for `TODO|FIXME|PLACEHOLDER` in `clod.py` returned no matches. No stub returns or empty handlers found in the wired code paths.

### Human Verification Required

These items need human testing with live services. Automated checks confirm the code paths are wired correctly; behavior verification requires a live session.

### 1. Mid-conversation model switch confirmation

**Test:** While chatting, run `/model deepseek-r1:14b` when `qwen2.5-coder:14b` is loaded
**Expected:** Confirmation prompt appears ("Unload qwen2.5-coder:14b and load deepseek-r1:14b?"), current model unloads with keep_alive:0, VRAM transition panel shows before/after, new model is warmup'd
**Why human:** Requires live Ollama instance and interactive REPL session

### 2. SD/ComfyUI launch with loaded Ollama model

**Test:** Load a model (visible via `/gpu`), then run `/sd image`
**Expected:** Terminal shows models being unloaded, VRAM transition panel appears ("GPU freed"), nvidia-smi check runs (warning shown only if VRAM not free), then SD starts via `sd_switch_mode`
**Why human:** Requires running Docker GPU services and physical RTX 4070 Ti SUPER GPU

### 3. Post-SD model restore prompt

**Test:** After `/sd image` has been running, run `/sd stop`
**Expected:** Services stop, GPU free VRAM is displayed, user is prompted whether to reload the previously loaded Ollama model
**Why human:** Requires Docker GPU services and a session where `_prev_model` was set by a prior SD launch

---

## Re-verification Summary

**All two previously failed gaps are now closed.** Plan 01-03 (commits a3bd735 and 5b29db7) wired the dead-code VRAM orchestration functions into the live slash command handlers:

1. **Gap 1 closed:** `/model` handler now calls `_ensure_model_ready` (line 2355) instead of `warmup_ollama_model` directly. `/gpu use` handler likewise (line 2512). `warmup_ollama_model` has zero direct calls from any slash handler — it only appears inside `_ensure_model_ready` and `_restore_after_gpu_service`.

2. **Gap 2 closed:** `/sd image|video` and `/sd start` handlers now call `_get_loaded_models` + `_unload_model` loop + `_verify_vram_free` before every `sd_switch_mode` call. `/sd stop` calls `_restore_after_gpu_service` to offer reloading the previous model.

**No regressions:** Full unit test suite (371 tests) passes in 181s. 8 new wiring tests added and all 29 tests in `test_vram.py` pass.

**Requirements VRAM-02 and VRAM-03** are now SATISFIED in practice, not just in isolation.

The phase goal is achieved: clod safely manages GPU memory across model loads and generation services, and clearly gates features based on connectivity.

---

_Verified: 2026-03-10T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
