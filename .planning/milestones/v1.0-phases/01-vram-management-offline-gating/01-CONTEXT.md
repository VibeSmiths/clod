# Phase 1: VRAM Management & Offline Gating - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Safe GPU memory lifecycle across Ollama model loads and SD/ComfyUI generation services, plus strict feature gating based on connectivity. This phase creates the foundation that all subsequent routing and generation features depend on.

</domain>

<decisions>
## Implementation Decisions

### Model Unload Behavior
- Use both layers: `OLLAMA_MAX_LOADED_MODELS=1` as safety net, plus explicit `keep_alive: 0` unload before known heavy transitions (SD launch, large model swap)
- Mid-conversation model switches require user confirmation ("This needs deepseek-r1. Switch? y/n") before proceeding
- After SD/ComfyUI generation completes, ask before reloading previous Ollama model ("Generation complete. Reload qwen2.5-coder:14b?")

### SD/ComfyUI GPU Handoff
- Before starting SD or ComfyUI, verify VRAM is actually free using nvidia-smi (not just trusting the unload call)
- SD/ComfyUI startup uses poll-until-ready pattern: show loading spinner, poll health endpoint every 2s until service responds (existing `_offer_docker_startup` pattern polls 90s)
- Full handoff sequence: unload Ollama model → verify VRAM via nvidia-smi → start SD/ComfyUI → poll until healthy

### Offline Mode
- Offline mode blocks cloud LLM calls (LiteLLM/Claude API) only — does NOT block local Docker services
- Web search (SearXNG) gets a separate independent toggle — SearXNG is local Docker but makes outbound internet requests
- Detection: health-based auto-detect from existing `_compute_features()` approach (LiteLLM down or no API key → auto-offline), plus manual `/offline` toggle
- Enforcement must be stricter than current: ensure no `requests.get/post` to cloud endpoints leaks through when offline

### Loading/Status UX
- Model operations show a Rich panel with VRAM usage numbers: "VRAM: 9.2/16.0 GB → Unloading... → 0.4/16.0 GB → Loading... → 8.8/16.0 GB"
- Always show VRAM before/after during model transitions (not just on errors)
- First-time model pulls show a progress bar with download size/speed (using Ollama pull API progress events)
- Quick model swaps (already pulled) show spinner inside the Rich panel

### Claude's Discretion
- Error recovery strategy when model unload fails (retry, restart Ollama, warn user)
- Exact polling interval and timeout for SD/ComfyUI health checks
- How to handle edge case where nvidia-smi is unavailable (e.g., WSL, Docker)
- Implementation of the `/search` toggle (new slash command or extend `/offline`)

</decisions>

<specifics>
## Specific Ideas

- "I want it to warn if it needs to switch modes or models at any point and have a loading dialog until the model swaps/is loaded"
- "When we are in offline mode, all calls out to the internet are stopped" — specifically cloud LLM calls; SearXNG is separate
- VRAM panel should feel informative, not alarming — show the numbers so user understands what's happening

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `query_gpu_vram()` (clod.py:503): Returns GPU VRAM info dict — reuse for VRAM verification
- `recommend_model_for_vram()` (clod.py:529): Maps VRAM to model — reuse for routing decisions
- `VRAM_TIERS` and `VRAM_CUDA_OVERHEAD_MB` constants: Established VRAM budget math
- `_check_service_health()` (clod.py:825): HTTP health checks for all services — extend for SD/ComfyUI readiness polling
- `_compute_features()` (clod.py:844): Feature flags from health + env — extend for stricter offline enforcement
- `_offer_docker_startup()`: Existing poll-until-ready pattern for Docker services (90s timeout)
- Rich console patterns: `console.print()` with markup for status, panels, progress bars

### Established Patterns
- Service health returns `dict[str, bool]` — consistent interface for all services
- Error handling: broad `except Exception:` with graceful degradation (return False, not raise)
- Session state dict carries `offline` flag, `features` dict, `health` dict across REPL turns
- Private functions prefixed with `_` for internal helpers
- Section comments: `# ── Section Name ─────────────────────────────`

### Integration Points
- `main()` (clod.py:~2677): Health checks and feature computation happen here before REPL — VRAM config goes here
- `infer()` (clod.py:~1997): Already checks `offline` flag — stricter enforcement hooks here
- `handle_slash()` (clod.py:~2079): `/offline` command at line 2163 — extend or add `/search` toggle
- `run_repl()` (clod.py:~2537): Session state initialization — VRAM manager state goes here
- `pick_adapter()`: Selects backend based on model + availability — offline gating extends this

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-vram-management-offline-gating*
*Context gathered: 2026-03-10*
