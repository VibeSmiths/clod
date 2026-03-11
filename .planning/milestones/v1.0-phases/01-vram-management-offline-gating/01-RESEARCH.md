# Phase 1: VRAM Management & Offline Gating - Research

**Researched:** 2026-03-10
**Domain:** GPU memory lifecycle management, connectivity-based feature gating
**Confidence:** HIGH

## Summary

Phase 1 is foundational infrastructure: safe GPU memory management across Ollama model loads and SD/ComfyUI services, plus strict offline gating. No new dependencies are needed -- everything builds on existing Ollama APIs, nvidia-smi subprocess calls, and the established health check / feature flag system already in clod.py.

The VRAM management layer uses two complementary mechanisms: `OLLAMA_MAX_LOADED_MODELS=1` as an environment-level safety net, and explicit `keep_alive:0` unload calls before heavy transitions (SD launch, large model swap). Verification happens via nvidia-smi (already implemented as `query_gpu_vram()`) and Ollama's `/api/ps` endpoint. The offline gating extends the existing `_compute_features()` and `session_state["offline"]` pattern to be stricter about blocking cloud HTTP calls.

All code changes go directly into `clod.py` -- no module extraction needed for this phase. The existing functions (`query_gpu_vram`, `_check_service_health`, `_compute_features`, `warmup_ollama_model`, `ollama_pull`) provide the foundation. New code adds VRAM transition management, Rich status panels, and tighter offline enforcement.

**Primary recommendation:** Build VRAM management as a set of functions in clod.py that wrap Ollama API calls with nvidia-smi verification, and extend the existing offline/features system for stricter gating.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Use both layers: `OLLAMA_MAX_LOADED_MODELS=1` as safety net, plus explicit `keep_alive: 0` unload before known heavy transitions (SD launch, large model swap)
- Mid-conversation model switches require user confirmation ("This needs deepseek-r1. Switch? y/n") before proceeding
- After SD/ComfyUI generation completes, ask before reloading previous Ollama model ("Generation complete. Reload qwen2.5-coder:14b?")
- Before starting SD or ComfyUI, verify VRAM is actually free using nvidia-smi (not just trusting the unload call)
- SD/ComfyUI startup uses poll-until-ready pattern: show loading spinner, poll health endpoint every 2s until service responds (existing `_offer_docker_startup` pattern polls 90s)
- Full handoff sequence: unload Ollama model -> verify VRAM via nvidia-smi -> start SD/ComfyUI -> poll until healthy
- Offline mode blocks cloud LLM calls (LiteLLM/Claude API) only -- does NOT block local Docker services
- Web search (SearXNG) gets a separate independent toggle -- SearXNG is local Docker but makes outbound internet requests
- Detection: health-based auto-detect from existing `_compute_features()` approach (LiteLLM down or no API key -> auto-offline), plus manual `/offline` toggle
- Enforcement must be stricter than current: ensure no `requests.get/post` to cloud endpoints leaks through when offline
- Model operations show a Rich panel with VRAM usage numbers: "VRAM: 9.2/16.0 GB -> Unloading... -> 0.4/16.0 GB -> Loading... -> 8.8/16.0 GB"
- Always show VRAM before/after during model transitions (not just on errors)
- First-time model pulls show a progress bar with download size/speed (using Ollama pull API progress events)
- Quick model swaps (already pulled) show spinner inside the Rich panel

### Claude's Discretion
- Error recovery strategy when model unload fails (retry, restart Ollama, warn user)
- Exact polling interval and timeout for SD/ComfyUI health checks
- How to handle edge case where nvidia-smi is unavailable (e.g., WSL, Docker)
- Implementation of the `/search` toggle (new slash command or extend `/offline`)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| VRAM-01 | Ollama configured with OLLAMA_MAX_LOADED_MODELS=1 to prevent OOM on 16GB GPU | Ollama env var documented in FAQ; set in .env and docker-compose |
| VRAM-02 | Before loading a new model, clod explicitly unloads the current model using Ollama's keep_alive:0 API | Ollama API supports `keep_alive: 0` with empty prompt to unload; verified via /api/ps |
| VRAM-03 | Before switching to SD/ComfyUI, clod unloads the active Ollama model to free GPU VRAM | Full handoff: unload via API -> verify via nvidia-smi -> start service -> poll health |
| OFFL-01 | When in offline mode, all outbound HTTP requests are blocked (no cloud LLM calls, no web search, no external API calls) | Extend existing `_compute_features()` + `pick_adapter()` gating; add guard in `infer()` |
| OFFL-02 | Offline mode auto-detected from service health checks and manually toggleable | Existing `_compute_features()` returns `offline_default`; `/offline` toggle exists at line 2163 |
| OFFL-03 | UI clearly indicates when offline mode is active | Rich panel/indicator in REPL header; update `print_header()` and status displays |
</phase_requirements>

## Standard Stack

### Core (No New Dependencies)

| Library/API | Version | Purpose | Why Standard |
|-------------|---------|---------|--------------|
| Ollama `/api/generate` | built-in | Model unload via `keep_alive:0` | Official Ollama API; empty prompt + keep_alive:0 unloads model immediately |
| Ollama `/api/ps` | built-in | Query currently loaded models | Returns model names, sizes, expiry times; verify unload completed |
| `OLLAMA_MAX_LOADED_MODELS` | env var | Limit concurrent loaded models | Default is 3; must set to 1 for 16 GB GPU to prevent OOM |
| nvidia-smi (subprocess) | system | VRAM verification | `query_gpu_vram()` already exists at clod.py:503; reuse for transition verification |
| Rich (Panel, Status, Progress) | already installed | VRAM transition UX | Already used throughout clod.py; `console.status()` for spinners, `Panel` for VRAM display |
| requests | already installed | HTTP calls to Ollama/health endpoints | Already used everywhere in clod.py |

### Supporting (Already Present)

| Library | Purpose | When to Use |
|---------|---------|-------------|
| `_check_service_health()` | Health check all services | Extend for SD/ComfyUI readiness polling |
| `_compute_features()` | Feature flags from health + env | Extend for stricter offline enforcement |
| `_offer_docker_startup()` | Poll-until-ready for Docker services | Reuse polling pattern for SD/ComfyUI startup |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| nvidia-smi subprocess | pynvml/py3nvml Python bindings | Adds dependency; nvidia-smi is always available with NVIDIA drivers and already works in `query_gpu_vram()` |
| Polling /api/ps for unload verification | Sleep-and-hope | Polling is deterministic; sleep may be too short or too long |
| Rich Panel for VRAM display | Plain text logging | Rich is already used everywhere; Panels match existing UX patterns |

## Architecture Patterns

### New Code Location

All new code goes in `clod.py` as new functions in existing sections. No module extraction for Phase 1.

```
clod.py (existing)
  # ── VRAM Management ─────────────  (NEW section, after line ~535)
  ├── _get_loaded_models(cfg)         # Query Ollama /api/ps
  ├── _unload_model(model, cfg)       # POST keep_alive:0
  ├── _verify_vram_free(min_free_mb)  # nvidia-smi check
  ├── _vram_transition_panel(...)     # Rich panel with before/after VRAM
  ├── _ensure_model_ready(target, cfg, console)  # Full load-with-UX flow
  └── _prepare_for_gpu_service(cfg, console)     # Full unload-verify flow for SD/ComfyUI

  # ── Offline Gating ──────────────  (extend existing section at ~844)
  ├── _compute_features()             # EXTEND: add web_search_enabled separate from offline
  ├── _is_cloud_request(model)        # Check if model prefix is cloud
  └── _enforce_offline(session_state)  # Guard function for outbound calls
```

### Pattern 1: Model Unload with Verification

**What:** Unload current Ollama model, verify VRAM is freed via nvidia-smi, with Rich status panel.
**When to use:** Before loading a different model, before starting SD/ComfyUI.

```python
# Ollama API: unload model
# Source: https://docs.ollama.com/faq
def _unload_model(model_name: str, cfg: dict) -> bool:
    """Unload a model by sending keep_alive=0 with empty prompt."""
    try:
        r = requests.post(
            f"{cfg['ollama_url']}/api/generate",
            json={"model": model_name, "keep_alive": 0, "prompt": ""},
            timeout=30,
        )
        return r.status_code == 200
    except Exception:
        return False

def _get_loaded_models(cfg: dict) -> list[dict]:
    """Query Ollama /api/ps for currently loaded models."""
    try:
        r = requests.get(f"{cfg['ollama_url']}/api/ps", timeout=5)
        return r.json().get("models", [])
    except Exception:
        return []

def _verify_vram_free(min_free_mb: int = 4000) -> bool:
    """Check nvidia-smi confirms enough free VRAM. Returns True if sufficient."""
    gpu = query_gpu_vram()
    if gpu is None:
        return True  # No nvidia-smi = can't verify, proceed optimistically
    return gpu["free_mb"] >= min_free_mb
```

**Confidence:** HIGH -- Ollama API for `keep_alive:0` and `/api/ps` are well-documented in official FAQ.

### Pattern 2: VRAM Transition Panel

**What:** Rich panel showing VRAM usage before, during, and after model transitions.
**When to use:** Every model load/unload operation.

```python
def _vram_transition_panel(phase: str, console_obj) -> None:
    """Show current VRAM state in a Rich panel."""
    gpu = query_gpu_vram()
    if gpu is None:
        return  # No GPU info available
    used_mb = gpu["total_mb"] - gpu["free_mb"]
    used_gb = used_mb / 1024
    total_gb = gpu["total_mb"] / 1024
    console_obj.print(
        f"  [dim]VRAM: {used_gb:.1f}/{total_gb:.1f} GB[/dim] [cyan]({phase})[/cyan]"
    )
```

**Confidence:** HIGH -- Uses existing `query_gpu_vram()` function and Rich patterns from codebase.

### Pattern 3: Full Model Swap with UX

**What:** Complete flow for switching Ollama models with confirmation, unload, verify, load, progress.
**When to use:** When user input requires a different model than currently loaded.

```python
def _ensure_model_ready(target: str, cfg: dict, console_obj, session_state: dict) -> bool:
    """Full model swap: unload current -> verify VRAM -> load target with UX."""
    current = session_state.get("model")
    loaded = _get_loaded_models(cfg)
    loaded_names = [m.get("name", "") for m in loaded]

    # Already loaded
    if target in loaded_names or f"{target}:latest" in loaded_names:
        return True

    # Unload current models
    for m in loaded:
        _vram_transition_panel("Unloading...", console_obj)
        _unload_model(m["name"], cfg)

    # Verify VRAM freed (poll up to 10s)
    for _ in range(5):
        if _verify_vram_free(2000):
            break
        time.sleep(2)

    _vram_transition_panel("Loading...", console_obj)

    # Check if model needs pulling first
    if not ollama_model_available(target, cfg["ollama_url"]):
        ollama_pull(target, cfg["ollama_url"])  # Shows progress bar
    else:
        # Quick swap: use warmup with spinner
        warmup_ollama_model(target, cfg)

    _vram_transition_panel("Ready", console_obj)
    session_state["model"] = target
    return True
```

### Pattern 4: SD/ComfyUI GPU Handoff

**What:** Full VRAM handoff sequence before starting GPU-intensive Docker services.
**When to use:** Before launching SD (AUTOMATIC1111) or ComfyUI.

```python
def _prepare_for_gpu_service(cfg: dict, console_obj) -> bool:
    """Unload Ollama model and verify VRAM before starting SD/ComfyUI."""
    loaded = _get_loaded_models(cfg)

    if loaded:
        console_obj.print("[dim]Freeing GPU for generation service...[/dim]")
        for m in loaded:
            _unload_model(m["name"], cfg)

        # Poll nvidia-smi until VRAM is free (timeout 15s)
        for i in range(8):
            gpu = query_gpu_vram()
            if gpu and gpu["free_mb"] > (gpu["total_mb"] - 2000):
                _vram_transition_panel("GPU freed", console_obj)
                return True
            time.sleep(2)

        # Timeout: warn but proceed
        console_obj.print("[yellow]VRAM may not be fully freed. Proceeding anyway.[/yellow]")

    return True
```

### Pattern 5: Offline Gating Extension

**What:** Stricter offline enforcement that catches all cloud HTTP paths.
**When to use:** Every outbound request decision point.

```python
# Extend _compute_features to separate web_search from offline
def _compute_features(env_vars: dict, health: dict) -> dict[str, bool]:
    _ant_key = env_vars.get("ANTHROPIC_API_KEY", "").strip()
    has_anthropic_key = bool(_ant_key) and "YOUR_KEY" not in _ant_key and "_HERE" not in _ant_key
    return {
        "cloud_models": health.get("litellm", False) and has_anthropic_key,
        "web_search": health.get("searxng", False),
        "web_search_enabled": True,  # NEW: separate toggle for SearXNG
        "semantic_recall": health.get("chroma", False),
        "pipelines": health.get("pipelines", False),
        "offline_default": not has_anthropic_key,
    }

# Guard for cloud requests
def _is_cloud_request(model: str) -> bool:
    return any(model.startswith(p) for p in CLOUD_MODEL_PREFIXES)
```

### Anti-Patterns to Avoid

- **Trusting unload without verification:** Do NOT assume `keep_alive:0` immediately frees VRAM. Always verify via nvidia-smi or `/api/ps` before proceeding with GPU-heavy operations.
- **Blocking on nvidia-smi unavailability:** If nvidia-smi is not available (WSL, Docker, non-NVIDIA GPU), proceed optimistically. Do not fail the operation. Log a warning.
- **Hardcoding VRAM thresholds:** Use constants derived from `VRAM_TIERS` and `VRAM_CUDA_OVERHEAD_MB` already defined in clod.py. Do not introduce new magic numbers.
- **Restarting Ollama as first error recovery:** Restart is a last resort. Try: retry unload -> wait longer -> warn user -> only then offer restart.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Model pull progress | Custom download tracking | `ollama_pull()` at line 419 | Already handles NDJSON progress events from Ollama API |
| Loading spinner | Custom animation loop | `console.status(spinner="dots")` | Already used by `warmup_ollama_model()` at line 484 |
| Service health polling | Custom HTTP polling loop | `_check_service_health()` pattern at line 825 | Extend existing health check with SD/ComfyUI endpoints |
| Docker service startup | Custom docker subprocess calls | `_offer_docker_startup()` pattern at line 869 | Existing poll-until-ready pattern with 90s timeout |
| GPU info query | pynvml bindings or custom parsing | `query_gpu_vram()` at line 503 | Already parses nvidia-smi CSV output correctly |
| Feature flag computation | Ad-hoc if/else chains | `_compute_features()` at line 844 | Pure function pattern, extend with new flags |

**Key insight:** Phase 1 is almost entirely about orchestrating existing primitives. The hard part is the state transitions and UX, not the individual operations.

## Common Pitfalls

### Pitfall 1: Ollama Silent CPU Fallback
**What goes wrong:** When Ollama cannot fit a model in VRAM, it silently falls back to CPU inference, which is 10-50x slower. The user sees no error -- just agonizingly slow responses.
**Why it happens:** `OLLAMA_MAX_LOADED_MODELS` defaults to 3. If two models are loaded on 16 GB, the third spills to CPU. Known issue: [ollama#11812](https://github.com/ollama/ollama/issues/11812).
**How to avoid:** Set `OLLAMA_MAX_LOADED_MODELS=1`. Always unload before loading. Verify via `/api/ps` that only target model is loaded after swap.
**Warning signs:** Inference taking >30s for simple prompts. `nvidia-smi` showing near-zero GPU utilization during inference.

### Pitfall 2: nvidia-smi Unavailable
**What goes wrong:** On WSL2, some Docker setups, or non-NVIDIA hardware, `nvidia-smi` is not in PATH. Code that requires nvidia-smi verification blocks all operations.
**Why it happens:** `query_gpu_vram()` already returns `None` on failure, but new verification code might not handle None gracefully.
**How to avoid:** Every nvidia-smi call must have a fallback path. If GPU info unavailable: log warning, skip VRAM verification step, proceed with operation. Never block on missing nvidia-smi.
**Warning signs:** `query_gpu_vram()` returns None in tests or on CI.

### Pitfall 3: Race Between Unload and Verify
**What goes wrong:** `keep_alive:0` returns 200 immediately, but VRAM is not freed for another 1-3 seconds. Immediate nvidia-smi check shows VRAM still occupied. Code either fails verification or enters infinite poll.
**Why it happens:** Ollama's unload is asynchronous internally. The HTTP response confirms the request, not the completion.
**How to avoid:** Poll `/api/ps` (not nvidia-smi) for model list -- empty list means unload complete. Use nvidia-smi as secondary verification. Poll interval: 1-2 seconds, timeout: 15 seconds.
**Warning signs:** Intermittent "VRAM not freed" warnings that resolve on retry.

### Pitfall 4: Offline Mode Leaks Cloud Calls
**What goes wrong:** Setting `session_state["offline"] = True` does not actually block all cloud paths. The `infer()` function at line 2006 redirects cloud models to local, but direct `requests.post` calls to LiteLLM elsewhere might bypass this check.
**Why it happens:** Offline enforcement is in `infer()` but the tool execution path (`execute_tool`) might call `search_web` or other tools that make outbound requests.
**How to avoid:** Enforce offline at two levels: (1) `pick_adapter()` returns `"cloud_unavailable"` when offline (already works for cloud models), (2) tool execution checks `session_state["offline"]` before any outbound HTTP call. The `search_web` tool already respects the `web_search` feature flag.
**Warning signs:** Network requests appearing in debug logs when `/offline` is active.

### Pitfall 5: SearXNG Toggle Confusion
**What goes wrong:** User expects `/offline` to block SearXNG (it makes internet requests) but SearXNG is a local Docker service. Or user wants SearXNG active while offline from cloud LLMs.
**Why it happens:** SearXNG is local infrastructure that makes outbound requests -- it straddles the offline/online boundary.
**How to avoid:** Separate `/offline` (cloud LLM gating) from `/search` (SearXNG toggle). The `web_search` feature flag in `_compute_features()` already tracks SearXNG health independently. Add `web_search_enabled` toggle that user controls via `/search on|off`.
**Warning signs:** User confusion about what "offline" means for SearXNG.

## Code Examples

### Ollama Model Unload (Verified)

```python
# Source: https://docs.ollama.com/faq
# Unload model immediately with empty prompt and keep_alive=0
requests.post(
    f"{cfg['ollama_url']}/api/generate",
    json={"model": "qwen2.5-coder:14b", "keep_alive": 0, "prompt": ""},
    timeout=30,
)
```

### Ollama Query Loaded Models (Verified)

```python
# Source: https://ollama.readthedocs.io/en/api/
# GET /api/ps returns {"models": [{"name": "...", "size": ..., ...}]}
r = requests.get(f"{cfg['ollama_url']}/api/ps", timeout=5)
loaded = r.json().get("models", [])
# Each model has: name, model, size, digest, details, expires_at, size_vram
```

### Rich Status Panel (Existing Pattern)

```python
# Source: clod.py line 484 -- warmup_ollama_model
with console.status(
    f"[dim]Loading [bold]{model}[/bold] into memory...[/dim]",
    spinner="dots",
):
    # ... blocking operation ...
```

### VRAM Panel Display (New, follows existing Rich patterns)

```python
# Matches Panel usage throughout clod.py (lines 294, 804, 879, etc.)
from rich.panel import Panel

gpu = query_gpu_vram()
if gpu:
    used_gb = (gpu["total_mb"] - gpu["free_mb"]) / 1024
    total_gb = gpu["total_mb"] / 1024
    console.print(Panel(
        f"[bold]VRAM:[/bold] {used_gb:.1f} / {total_gb:.1f} GB\n"
        f"[dim]Free: {gpu['free_mb'] / 1024:.1f} GB[/dim]",
        title="[cyan]GPU Status[/cyan]",
        border_style="cyan",
        expand=False,
    ))
```

### Offline Guard in infer() (Extend Existing)

```python
# Source: clod.py line 2006 -- existing offline check
# Current: redirects cloud models to local default
# EXTEND: also block tool calls that require internet
if offline:
    pipeline = None
    if any(model.startswith(p) for p in CLOUD_MODEL_PREFIXES):
        model = cfg["default_model"]
        console.print(f"[dim][offline] using local model: {model}[/dim]")
    # NEW: enforce in tool execution too
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `OLLAMA_MAX_LOADED_MODELS=3` (default) | Set to 1 for 16 GB GPUs | Ollama docs recommendation | Prevents OOM and silent CPU fallback |
| No explicit unload | `keep_alive:0` API | Available since Ollama 0.1.x | Deterministic VRAM release |
| Trust unload completed | Verify via `/api/ps` + nvidia-smi | Best practice | Catches async unload delays |
| Global offline toggle | Separate offline (cloud) + search (SearXNG) toggles | This phase | Users control each independently |

## Discretion Recommendations

### Error Recovery When Model Unload Fails
**Recommendation:** Three-tier recovery:
1. **Retry** (1 attempt, 5s wait) -- most transient failures resolve
2. **Force via Ollama restart** -- `docker restart ollama` if retry fails, only if Ollama is in Docker
3. **Warn and proceed** -- if neither works, warn user that VRAM may not be fully freed, let them decide

### Polling Interval and Timeout for SD/ComfyUI Health Checks
**Recommendation:** 2-second interval, 60-second timeout (not 90s like `_offer_docker_startup`). SD/ComfyUI are already pulled/built; the startup time is just GPU initialization and model loading. 60s is generous. Show countdown in Rich status.

### nvidia-smi Unavailable
**Recommendation:** Graceful degradation. `query_gpu_vram()` already returns None. When None:
- Skip VRAM verification step entirely
- Log `[dim]GPU monitoring unavailable -- skipping VRAM verification[/dim]`
- Proceed with operation as if VRAM is available
- Set a session-level flag `session_state["gpu_monitoring"] = False` to avoid repeated warnings

### /search Toggle Implementation
**Recommendation:** New `/search` slash command (not extending `/offline`). Clean separation:
- `/offline` -- toggles cloud LLM blocking (existing, extend)
- `/search` or `/search on|off` -- toggles SearXNG web search independently
- Both show current state in output: `[dim]Offline: ON | Web search: OFF[/dim]`
- `/offline` does NOT change search state; `/search` does NOT change offline state

## Open Questions

1. **Ollama unload timing variance**
   - What we know: `keep_alive:0` returns 200 immediately; actual VRAM free takes 1-3 seconds
   - What's unclear: Is there a callback/event for unload completion, or must we poll?
   - Recommendation: Poll `/api/ps` until model list is empty; timeout at 15s

2. **OLLAMA_MAX_LOADED_MODELS enforcement mechanism**
   - What we know: The env var limits concurrent models in VRAM
   - What's unclear: Where is it set? Docker env? System env? .env file?
   - Recommendation: Set in docker-compose.yml environment section for Ollama service, AND in .env as backup. `_ensure_local_configs()` already handles .env management.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + coverage |
| Config file | None (pytest invoked via command line) |
| Quick run command | `python -m pytest tests/unit/test_startup.py tests/unit/test_vram.py -x -q` |
| Full suite command | `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VRAM-01 | OLLAMA_MAX_LOADED_MODELS=1 is set | unit | `python -m pytest tests/unit/test_vram.py::test_env_config -x` | No -- Wave 0 |
| VRAM-02 | Unload current model before loading new one | unit | `python -m pytest tests/unit/test_vram.py::test_unload_before_load -x` | No -- Wave 0 |
| VRAM-03 | Unload model before SD/ComfyUI launch | unit | `python -m pytest tests/unit/test_vram.py::test_prepare_for_gpu_service -x` | No -- Wave 0 |
| OFFL-01 | Offline blocks cloud HTTP calls | unit | `python -m pytest tests/unit/test_offline.py::test_offline_blocks_cloud -x` | No -- Wave 0 |
| OFFL-02 | Auto-detect offline from health + manual toggle | unit | `python -m pytest tests/unit/test_startup.py::test_compute_features_offline -x` | Partial (test_startup.py has _compute_features tests) |
| OFFL-03 | UI shows offline indicator | unit | `python -m pytest tests/unit/test_offline.py::test_offline_indicator -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/test_vram.py tests/unit/test_offline.py -x -q`
- **Per wave merge:** `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_vram.py` -- covers VRAM-01, VRAM-02, VRAM-03 (new file)
- [ ] `tests/unit/test_offline.py` -- covers OFFL-01, OFFL-03 (new file)
- [ ] Extend `tests/unit/test_startup.py` -- OFFL-02 partially covered, may need new tests for extended `_compute_features()`
- [ ] Mock patterns: `responses` library for Ollama API mocking (already used in test suite), `monkeypatch` for `query_gpu_vram` (subprocess mock)

## Sources

### Primary (HIGH confidence)
- [Ollama FAQ - Model Unloading](https://docs.ollama.com/faq) -- `keep_alive:0`, `OLLAMA_MAX_LOADED_MODELS`, `/api/ps` endpoint
- [Ollama API Reference](https://ollama.readthedocs.io/en/api/) -- `/api/generate`, `/api/ps` endpoint details
- clod.py source code -- `query_gpu_vram()` (line 503), `_check_service_health()` (line 825), `_compute_features()` (line 844), `warmup_ollama_model()` (line 478), `ollama_pull()` (line 419)

### Secondary (MEDIUM confidence)
- [Unloading Ollama Models Practically](https://pauleasterbrooks.com/articles/technology/clearing-ollama-memory) -- Practical guide to keep_alive=0 usage
- [Ollama Issue #11812](https://github.com/ollama/ollama/issues/11812) -- Silent CPU fallback after VRAM spill
- [nvidia-smi query reference](https://nvidia.custhelp.com/app/answers/detail/a_id/3751/~/useful-nvidia-smi-queries) -- Query formats for GPU memory

### Tertiary (LOW confidence)
- None -- all findings verified with primary sources

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all APIs verified against official docs
- Architecture: HIGH -- extends existing code patterns, integration points clearly identified
- Pitfalls: HIGH -- VRAM exhaustion and CPU fallback are well-documented Ollama issues
- Validation: HIGH -- test patterns match existing test suite conventions

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable domain, Ollama API unlikely to change)
