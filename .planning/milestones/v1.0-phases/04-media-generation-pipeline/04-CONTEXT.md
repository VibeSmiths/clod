# Phase 4: Media Generation Pipeline - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Users generate images and videos through natural language or explicit `/generate` commands, with automatic docker profile orchestration. Clod crafts optimized prompts via llama3.1:8b, manages VRAM handoffs between LLM and generation services, and handles the full lifecycle from intent detection through output display. Face swap is a separate phase (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### Prompt Crafting Pipeline
- Single-shot prompt crafting via llama3.1:8b with SD-optimized system prompt — no conversational refinement
- Show crafted prompt briefly and auto-proceed (like Phase 3's "Switching to..." pattern) — user sees what's happening without being blocked
- Auto-append default negative prompts per SD model type: SD1.5 negatives differ from SDXL negatives
- Detect SD model type by querying AUTOMATIC1111 API (`/sdapi/v1/options` → checkpoint name → match "sdxl"/"xl" pattern); fallback to SD1.5 if unreachable
- Same pipeline for video generation but with a ComfyUI-optimized system prompt — same model (llama3.1:8b), different instructions
- Parse user exclusions from natural language ("but no people") and add them to negative prompts

### Generation Trigger Flow
- When intent detects image_gen/video_gen but service isn't running: offer to start with confirmation ("Start image mode? This will unload current model...") — consistent with Phase 1's `_offer_docker_startup` pattern
- VRAM handoff sequence: load llama3.1:8b → craft prompt → unload llama3.1 → start SD/ComfyUI → generate — sequential, safe
- After generation completes: auto-reload previous Ollama model silently (no confirmation prompt)
- `/generate image <prompt>` and `/generate video <prompt>` as explicit slash command fallbacks — skip intent detection, go directly to prompt crafting

### Docker Profile Orchestration
- Warn and confirm before profile switches: "Switching from image to video mode. This will stop AUTOMATIC1111 and start ComfyUI. Continue?" — matches DOCK-02 requirement
- GPU release verification via nvidia-smi polling after stopping a service — poll until VRAM drops below threshold before starting the new service
- Clod calls AUTOMATIC1111's `/sdapi/v1/txt2img` API directly (not via Open-WebUI) — full control over parameters, existing `sd_check()` already talks to localhost:7860
- ComfyUI integration via direct API as well — queue prompts and poll for results

### Output Handling
- Images saved to `${SD_OUTPUT_DIR}` (existing docker-compose path), videos to `${COMFYUI_OUTPUT_DIR}`
- Naming convention: `clod_{timestamp}_{short_hash}.{ext}` (e.g., `clod_20260310_143022_a1b2.png`)
- Auto-open in system default viewer/player via `os.startfile` (Windows) after generation
- Show Rich progress during SD generation: poll `/sdapi/v1/progress` for step count + ETA
- Same save + auto-open pattern for both images and videos

### Claude's Discretion
- Exact system prompts for llama3.1:8b (SD and ComfyUI variants)
- Default generation parameters (steps, CFG scale, sampler, dimensions)
- ComfyUI workflow JSON structure and API integration approach
- nvidia-smi polling interval and timeout thresholds
- Error handling for failed generations or API timeouts

</decisions>

<specifics>
## Specific Ideas

- VRAM flow preview from Phase 1 context: "I want it to warn if it needs to switch modes or models at any point and have a loading dialog until the model swaps/is loaded"
- Phase 3 already has `INTENT_MODEL_MAP` with `image_gen: None` and `video_gen: None` placeholders ready for Phase 4 wiring
- Generation progress should feel like Phase 3's Rich Progress bars — consistent UX across pull progress and generation progress
- `/generate` commands provide a reliable fallback when intent detection isn't confident enough

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `INTENT_MODEL_MAP` (clod.py:97): Has `image_gen: None` and `video_gen: None` placeholders — Phase 4 wires these to trigger generation instead of model routing
- `_route_to_model()` (clod.py:687): Early-returns on `None` targets — Phase 4 intercepts `None`-mapped intents before this function
- `sd_switch_mode()` (clod.py:1513): Existing docker profile switcher — reuse for auto-switching on intent detection
- `query_comfyui_running()` (clod.py:847): Health check for AUTOMATIC1111 — extend for service readiness during generation flow
- `comfyui_docker_action()` (clod.py:876): Docker actions for ComfyUI — reuse for video profile management
- `SD_WEBUI_URL` constant (clod.py:68): `http://localhost:7860` — base URL for AUTOMATIC1111 API calls
- `_offer_docker_startup()`: Poll-until-ready pattern for docker services — reuse for generation service startup
- `query_gpu_vram()` (clod.py:503): nvidia-smi VRAM query — reuse for VRAM polling during profile switches
- Rich Progress patterns from Phase 3 (`ollama_pull`): Reuse for generation progress display

### Established Patterns
- Session state dict carries `model`, `offline`, `features`, `health` — extend with generation state
- `/sd` command tree in `handle_slash()` (clod.py:2593): Existing pattern for SD-related commands — add `/generate` nearby
- Confirm-before-switch UX from Phase 3 routing: cyan message + auto-proceed
- VRAM handoff: unload → verify → start → poll (Phase 1 pattern)

### Integration Points
- `_route_to_model()` returns early for `None` targets — Phase 4 adds an `elif target is None` branch to handle generation intents
- `handle_slash()`: Add `/generate image|video` command handling
- `run_repl()`: Generation results need to be displayed inline (Rich panel with file path + viewer launch)
- `INTENT_MODEL_MAP`: Update `image_gen` and `video_gen` entries (or keep None and handle specially in routing)

</code_context>

<deferred>
## Deferred Ideas

- Image-edit sub-intent handling (modify existing images) — may need its own downstream handling beyond generation
- Style presets library (`/style cinematic`, `/style anime`) — IMG-05 is explicitly v2
- Iterative prompt refinement ("make it more dramatic") — IMG-06 is explicitly v2

</deferred>

---

*Phase: 04-media-generation-pipeline*
*Context gathered: 2026-03-10*
