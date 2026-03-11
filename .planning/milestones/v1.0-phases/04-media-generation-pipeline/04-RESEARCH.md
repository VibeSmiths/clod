# Phase 4: Media Generation Pipeline - Research

**Researched:** 2026-03-10
**Domain:** AUTOMATIC1111 API, ComfyUI API, Docker profile orchestration, LLM prompt crafting
**Confidence:** HIGH

## Summary

Phase 4 wires the existing intent classification system (image_gen/video_gen intents currently mapped to `None`) into actual generation pipelines. The core flow is: detect intent -> load llama3.1:8b -> craft optimized prompt -> unload LLM -> start generation service -> poll progress -> save output -> auto-open -> restore previous model. Two external APIs are involved: AUTOMATIC1111's REST API (`/sdapi/v1/txt2img`) for images and ComfyUI's queue-based API (`/prompt` + `/history`) for video.

The codebase already has substantial infrastructure: `_prepare_for_gpu_service()` handles VRAM handoff, `sd_switch_mode()` manages Docker profile switches, `query_comfyui_running()` and `query_video_running()` check service health, and `_restore_after_gpu_service()` handles model reload. Phase 4 needs to: (1) intercept None-mapped intents in the routing path, (2) build prompt crafting via Ollama chat API, (3) implement direct AUTOMATIC1111/ComfyUI API calls, (4) add progress display, and (5) wire `/generate` as a slash command.

**Primary recommendation:** Build the generation pipeline as a set of composable functions (craft_prompt, generate_image, generate_video, handle_generation_intent) that reuse existing VRAM/Docker infrastructure rather than duplicating it. The AUTOMATIC1111 integration is straightforward REST; ComfyUI requires a poll-based approach (POST /prompt, poll GET /history/{id}).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Single-shot prompt crafting via llama3.1:8b with SD-optimized system prompt -- no conversational refinement
- Show crafted prompt briefly and auto-proceed (like Phase 3's "Switching to..." pattern)
- Auto-append default negative prompts per SD model type: SD1.5 negatives differ from SDXL negatives
- Detect SD model type by querying AUTOMATIC1111 API (`/sdapi/v1/options` -> checkpoint name -> match "sdxl"/"xl" pattern); fallback to SD1.5 if unreachable
- Same pipeline for video generation but with a ComfyUI-optimized system prompt
- Parse user exclusions from natural language ("but no people") and add them to negative prompts
- Warn and confirm before profile switches; GPU release verification via nvidia-smi polling
- Clod calls AUTOMATIC1111's `/sdapi/v1/txt2img` API directly (not via Open-WebUI)
- ComfyUI integration via direct API
- Images saved to `${SD_OUTPUT_DIR}`, videos to `${COMFYUI_OUTPUT_DIR}`
- Naming convention: `clod_{timestamp}_{short_hash}.{ext}`
- Auto-open in system default viewer via `os.startfile` (Windows) after generation
- Show Rich progress during SD generation: poll `/sdapi/v1/progress` for step count + ETA
- VRAM handoff: load llama3.1:8b -> craft prompt -> unload -> start SD/ComfyUI -> generate -- sequential
- After generation: auto-reload previous Ollama model silently (no confirmation prompt)
- `/generate image <prompt>` and `/generate video <prompt>` as explicit slash command fallbacks

### Claude's Discretion
- Exact system prompts for llama3.1:8b (SD and ComfyUI variants)
- Default generation parameters (steps, CFG scale, sampler, dimensions)
- ComfyUI workflow JSON structure and API integration approach
- nvidia-smi polling interval and timeout thresholds
- Error handling for failed generations or API timeouts

### Deferred Ideas (OUT OF SCOPE)
- Image-edit sub-intent handling (modify existing images)
- Style presets library (`/style cinematic`, `/style anime`) -- IMG-05 is v2
- Iterative prompt refinement ("make it more dramatic") -- IMG-06 is v2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| IMG-01 | User triggers image generation via natural language | Intent classification already detects `image_gen`; Phase 4 intercepts `None` target in `_route_to_model()` |
| IMG-02 | Chat model crafts SD-optimized prompt from user description | Single-shot Ollama chat call to llama3.1:8b with SD system prompt; extract structured prompt |
| IMG-03 | Default negative prompts auto-appended by SD model type | GET `/sdapi/v1/options` -> `sd_model_checkpoint` -> pattern match sdxl/xl; select appropriate negatives |
| IMG-04 | If AUTOMATIC1111 not running, offer to start image docker profile | Reuse `_offer_docker_startup()` / `_prepare_for_gpu_service()` patterns |
| VID-01 | User triggers video generation via natural language | Intent classification already detects `video_gen`; same interception pattern as IMG-01 |
| VID-02 | Chat model crafts ComfyUI-optimized prompt | Same llama3.1:8b pipeline, different system prompt for video-oriented descriptions |
| VID-03 | If ComfyUI not running, offer to switch docker profiles with GPU release verification | Reuse `sd_switch_mode()` + `_verify_vram_free()` polling; add confirmation UX |
| DOCK-01 | Auto-detect when docker profile switch needed | Check `query_comfyui_running()` / `query_video_running()` before generation; determine if switch needed |
| DOCK-02 | Warn user and confirm before profile switch | Confirmation prompt before calling `sd_switch_mode()` with profile name and impact message |
| DOCK-03 | GPU release verification during profile switch | `_verify_vram_free()` polling with nvidia-smi; already implemented in `_prepare_for_gpu_service()` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| requests | (already imported) | HTTP calls to AUTOMATIC1111 and ComfyUI APIs | Already used throughout codebase |
| base64 | (stdlib) | Decode AUTOMATIC1111 image responses | A1111 returns images as base64 strings |
| hashlib | (stdlib) | Generate short hash for file naming | `clod_{timestamp}_{hash}.png` convention |
| os.startfile | (stdlib, Windows) | Auto-open generated files | Windows-specific, already the target platform |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich.progress | (already imported) | Generation progress bars | Poll `/sdapi/v1/progress` during image generation |
| json | (stdlib) | ComfyUI workflow JSON construction | Building workflow payloads for `/prompt` endpoint |
| urllib.parse | (already imported) | ComfyUI `/view` endpoint URL construction | Downloading output files from ComfyUI |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct HTTP to ComfyUI | comfy-api-simplified PyPI | Adds dependency; direct HTTP is simple enough for queue+poll |
| WebSocket for ComfyUI progress | HTTP polling /history | WebSocket is more responsive but adds complexity; polling /history is sufficient for MVP |
| PIL/Pillow for image handling | Raw base64 decode | No image processing needed -- just save bytes to file |

**Installation:**
No new dependencies required. All needed libraries are already in the project.

## Architecture Patterns

### Recommended Project Structure
```
clod.py  (all in single file, following existing pattern)
  +-- _craft_sd_prompt()           # llama3.1:8b -> SD-optimized prompt
  +-- _craft_video_prompt()        # llama3.1:8b -> ComfyUI-optimized prompt
  +-- _detect_sd_model_type()      # GET /sdapi/v1/options -> "sd15" | "sdxl"
  +-- _get_negative_prompts()      # model_type -> default negatives + user exclusions
  +-- _generate_image()            # POST /sdapi/v1/txt2img + progress polling
  +-- _generate_video()            # POST ComfyUI /prompt + poll /history
  +-- _save_generation_output()    # Save to output dir with naming convention
  +-- _handle_generation_intent()  # Orchestrator: intent -> craft -> generate -> save -> open
  +-- handle_slash /generate       # Explicit command entry point
```

### Pattern 1: Intent Interception for Generation
**What:** Intercept `None`-mapped intents before they reach `_route_to_model()`'s early return
**When to use:** When intent classification detects image_gen or video_gen with confidence >= 0.8
**Example:**
```python
# In the REPL loop, after intent classification, before _route_to_model():
if HAS_INTENT and session_state["intent_enabled"]:
    intent, confidence = classify_intent(user_input)
    # ... existing logging ...
    if confidence >= 0.8:
        target = INTENT_MODEL_MAP.get(intent)
        if target is None and intent in ("image_gen", "video_gen"):
            # Phase 4: handle generation intent
            _handle_generation_intent(
                intent, user_input, session_state, console, cfg
            )
            continue  # skip normal infer() flow
        _route_to_model(intent, confidence, session_state, console)
```

### Pattern 2: Prompt Crafting via Ollama Chat API
**What:** Use llama3.1:8b as a prompt engineer -- send user request, get back SD/ComfyUI-optimized prompt
**When to use:** Before every generation request
**Example:**
```python
def _craft_sd_prompt(user_request: str, cfg: dict) -> tuple[str, str]:
    """Craft an SD-optimized prompt from user's natural language.
    Returns (positive_prompt, user_exclusions)."""
    system = SD_PROMPT_SYSTEM  # crafting instructions
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_request},
    ]
    r = requests.post(
        f"{cfg['ollama_url']}/api/chat",
        json={"model": "llama3.1:8b", "messages": messages, "stream": False},
        timeout=60,
    )
    response_text = r.json()["message"]["content"]
    # Parse out the optimized prompt and any user exclusions
    return _parse_crafted_prompt(response_text)
```

### Pattern 3: AUTOMATIC1111 txt2img with Progress Polling
**What:** Submit generation, poll progress, save result
**When to use:** Image generation via AUTOMATIC1111
**Example:**
```python
import base64, hashlib, time
from datetime import datetime

def _generate_image(prompt: str, negative: str, cfg: dict, console_obj) -> str | None:
    """Generate image via A1111 API. Returns saved file path or None."""
    payload = {
        "prompt": prompt,
        "negative_prompt": negative,
        "steps": 25,
        "cfg_scale": 7,
        "width": 512,     # SD1.5 default; 1024 for SDXL
        "height": 512,
        "sampler_name": "DPM++ 2M",
        "save_images": False,  # we save ourselves with naming convention
    }
    # Submit in background thread, poll progress in main thread
    # ... (see Code Examples section for full pattern)
```

### Pattern 4: ComfyUI Queue + Poll
**What:** POST workflow JSON to /prompt, poll /history/{id} for completion, download via /view
**When to use:** Video generation via ComfyUI
**Example:**
```python
def _generate_video(prompt: str, cfg: dict, console_obj) -> str | None:
    """Generate video via ComfyUI API. Returns saved file path or None."""
    workflow = _build_video_workflow(prompt)  # Construct workflow JSON
    r = requests.post(
        f"{COMFYUI_URL}/prompt",
        json={"prompt": workflow},
        timeout=30,
    )
    prompt_id = r.json()["prompt_id"]
    # Poll /history/{prompt_id} until complete
    # ... (see Code Examples section)
```

### Anti-Patterns to Avoid
- **Blocking the main thread during generation:** Use threading for the HTTP POST to txt2img (which blocks until complete) while polling progress on main thread. Or accept blocking since this is a CLI.
- **Re-implementing VRAM management:** Don't duplicate `_prepare_for_gpu_service()` logic; call it or compose from its primitives.
- **Hardcoding output paths:** Read from cfg/env vars (`SD_OUTPUT_DIR`, `COMFYUI_OUTPUT_DIR`), don't hardcode.
- **Polling progress too frequently:** AUTOMATIC1111's `/sdapi/v1/progress` slows generation if polled faster than ~1s intervals. Use `skip_current_image=true` to avoid base64 overhead.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SD prompt optimization | Custom NLP pipeline | System prompt for llama3.1:8b | LLM already understands SD prompt style (comma-separated tags, quality keywords) |
| VRAM lifecycle | New unload/verify flow | `_prepare_for_gpu_service()`, `_unload_model()`, `_verify_vram_free()` | Already tested and working in Phase 1 |
| Docker profile switching | Direct docker commands | `sd_switch_mode()` | Handles .env update, service stop/start, Open-WebUI restart |
| Service health detection | New health check | `query_comfyui_running()`, `query_video_running()` | Existing functions check localhost:7860 and localhost:8188 |
| Model restore after generation | Custom state tracking | `session_state["_prev_model"]` pattern | Already used by `_prepare_for_gpu_service()` |

**Key insight:** Phase 4's infrastructure layer is 80% already built. The new work is the generation API integration, prompt crafting, and orchestration glue.

## Common Pitfalls

### Pitfall 1: AUTOMATIC1111 txt2img Blocks Until Complete
**What goes wrong:** POST to `/sdapi/v1/txt2img` does not return until generation finishes. If you wait for the response, you cannot poll progress.
**Why it happens:** The API is synchronous -- it generates and returns the image in one response.
**How to avoid:** Use `threading.Thread` to run the POST in background; poll `/sdapi/v1/progress` from the main thread with Rich progress bar. Or use `concurrent.futures.ThreadPoolExecutor`.
**Warning signs:** Progress bar never updates, then suddenly jumps to 100%.

### Pitfall 2: Progress Polling Overhead
**What goes wrong:** Polling `/sdapi/v1/progress` too frequently (< 1s) significantly slows generation.
**Why it happens:** Each progress request forces A1111 to serialize state; with `current_image` enabled it base64-encodes the WIP image.
**How to avoid:** Poll every 1-2 seconds. Always pass `skip_current_image=true` in the query string.
**Warning signs:** Generation takes 2-3x longer than in the WebUI.

### Pitfall 3: SD Model Type Detection Failure
**What goes wrong:** GET `/sdapi/v1/options` fails or returns unexpected checkpoint name format.
**Why it happens:** Service might be loading, model name might not contain "xl"/"sdxl" (some models use different naming).
**How to avoid:** Fallback to SD1.5 negatives if detection fails. Pattern match case-insensitive on checkpoint name for "xl", "sdxl", "pony" (PonyXL is SDXL-based).
**Warning signs:** SDXL model getting SD1.5-style verbose negative prompts (harmless but suboptimal).

### Pitfall 4: ComfyUI Workflow JSON Structure
**What goes wrong:** ComfyUI expects a specific node-graph JSON format, not just a prompt string. Invalid workflow JSON silently fails.
**Why it happens:** ComfyUI is node-based; the API expects the full workflow graph with node IDs and connections.
**How to avoid:** Create the workflow JSON by designing a basic text-to-video workflow in ComfyUI UI first, export it via "Save (API format)", then parameterize it in code. Ship a default workflow template.
**Warning signs:** POST to /prompt returns error with `node_errors`.

### Pitfall 5: os.startfile Cross-Platform
**What goes wrong:** `os.startfile()` only exists on Windows. Code crashes on Linux/WSL.
**Why it happens:** Windows-only stdlib function.
**How to avoid:** Guard with `if hasattr(os, 'startfile')` or `platform.system() == 'Windows'`. Could fall back to `subprocess.run(["xdg-open", path])` on Linux, but project is Windows-first.
**Warning signs:** AttributeError on non-Windows platforms.

### Pitfall 6: VRAM Not Freed Before Generation Service Start
**What goes wrong:** Starting SD/ComfyUI while an Ollama model is still loaded causes CUDA OOM.
**Why it happens:** Ollama model unload is async; VRAM isn't immediately freed after the API call.
**How to avoid:** Use existing `_verify_vram_free()` polling with threshold check before starting generation service. The `_prepare_for_gpu_service()` function already does this correctly.
**Warning signs:** SD/ComfyUI crashes on startup with CUDA out of memory.

### Pitfall 7: Auto-Reload Changes Behavior from Existing Code
**What goes wrong:** Current `_restore_after_gpu_service()` prompts user with y/N. CONTEXT.md says auto-reload silently.
**Why it happens:** Phase 4 changes the restore behavior from interactive to automatic.
**How to avoid:** Create a new restore function or add a `silent=True` parameter. Don't modify the existing function's default behavior (it's used by `/sd stop`).
**Warning signs:** Tests for existing restore behavior break.

## Code Examples

### Complete Image Generation Flow
```python
import base64
import hashlib
import os
import threading
import time
from datetime import datetime

def _generate_image(
    prompt: str,
    negative: str,
    params: dict,
    cfg: dict,
    console_obj,
) -> str | None:
    """Generate image via AUTOMATIC1111 API with progress display.
    Returns saved file path or None on failure."""
    payload = {
        "prompt": prompt,
        "negative_prompt": negative,
        "steps": params.get("steps", 25),
        "cfg_scale": params.get("cfg_scale", 7),
        "width": params.get("width", 512),
        "height": params.get("height", 512),
        "sampler_name": params.get("sampler", "DPM++ 2M"),
        "save_images": False,
    }

    result_holder = {"response": None, "error": None}

    def _do_generate():
        try:
            r = requests.post(
                f"{SD_WEBUI_URL}/sdapi/v1/txt2img",
                json=payload,
                timeout=300,
            )
            r.raise_for_status()
            result_holder["response"] = r.json()
        except Exception as e:
            result_holder["error"] = str(e)

    thread = threading.Thread(target=_do_generate)
    thread.start()

    # Poll progress with Rich Progress bar
    with Progress(
        TextColumn("[cyan]{task.description}"),
        BarColumn(),
        TextColumn("{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console_obj,
    ) as progress:
        task = progress.add_task("Generating...", total=100)
        while thread.is_alive():
            try:
                pr = requests.get(
                    f"{SD_WEBUI_URL}/sdapi/v1/progress?skip_current_image=true",
                    timeout=5,
                )
                data = pr.json()
                pct = data.get("progress", 0) * 100
                progress.update(task, completed=pct)
            except Exception:
                pass
            time.sleep(1.5)
        progress.update(task, completed=100)

    thread.join()

    if result_holder["error"] or not result_holder["response"]:
        console_obj.print(f"[red]Generation failed: {result_holder['error']}[/red]")
        return None

    # Save image
    images = result_holder["response"].get("images", [])
    if not images:
        return None

    img_data = base64.b64decode(images[0].split(",", 1)[-1])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    short_hash = hashlib.md5(img_data[:256]).hexdigest()[:4]
    filename = f"clod_{ts}_{short_hash}.png"
    output_dir = cfg.get("sd_output_dir", ".")
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "wb") as f:
        f.write(img_data)

    return filepath
```

### SD Model Type Detection
```python
def _detect_sd_model_type() -> str:
    """Detect whether loaded SD model is SDXL or SD1.5.
    Returns 'sdxl' or 'sd15'. Falls back to 'sd15'."""
    try:
        r = requests.get(f"{SD_WEBUI_URL}/sdapi/v1/options", timeout=5)
        if r.status_code == 200:
            checkpoint = r.json().get("sd_model_checkpoint", "").lower()
            if any(tag in checkpoint for tag in ("sdxl", "xl", "pony")):
                return "sdxl"
    except Exception:
        pass
    return "sd15"
```

### Default Negative Prompts
```python
SD15_NEGATIVES = (
    "low quality, worst quality, ugly, blurry, extra limbs, extra fingers, "
    "mutated hands, poorly drawn hands, poorly drawn face, deformed, "
    "disfigured, watermark, text, signature, out of frame"
)

SDXL_NEGATIVES = (
    "low quality, worst quality, watermark, text, signature"
)

def _get_negative_prompts(model_type: str, user_exclusions: str = "") -> str:
    """Combine default negatives with user exclusions."""
    base = SDXL_NEGATIVES if model_type == "sdxl" else SD15_NEGATIVES
    if user_exclusions:
        return f"{base}, {user_exclusions}"
    return base
```

### Prompt Crafting System Prompt (Recommended)
```python
SD_PROMPT_SYSTEM = """You are a Stable Diffusion prompt engineer. Convert the user's natural language description into an optimized SD prompt.

Rules:
1. Output ONLY the optimized prompt, nothing else
2. Use comma-separated tags and descriptive phrases
3. Include quality boosters: masterpiece, best quality, highly detailed
4. Include relevant style/lighting/composition terms
5. If the user mentions things to exclude (e.g., "but no people"), output them on a second line prefixed with EXCLUDE:

Example input: "a sunset over mountains, but no clouds"
Example output:
masterpiece, best quality, sunset over mountain range, golden hour, dramatic sky, vivid colors, landscape photography, highly detailed
EXCLUDE: clouds"""

VIDEO_PROMPT_SYSTEM = """You are a video generation prompt engineer. Convert the user's description into an optimized prompt for AI video generation.

Rules:
1. Output ONLY the optimized prompt, nothing else
2. Describe motion and temporal progression
3. Include camera movement if appropriate (pan, zoom, tracking shot)
4. Specify style and mood
5. Keep it concise (1-3 sentences)

Example input: "a cat dancing"
Example output:
A fluffy orange cat performing playful dance moves, swaying side to side with front paws raised, smooth motion, soft natural lighting, cinematic quality, 4K"""
```

### ComfyUI Video Generation (Poll-based)
```python
def _generate_video(
    prompt: str,
    cfg: dict,
    console_obj,
) -> str | None:
    """Generate video via ComfyUI API. Returns saved file path or None."""
    workflow = _build_video_workflow(prompt)

    try:
        r = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow},
            timeout=30,
        )
        r.raise_for_status()
        prompt_id = r.json()["prompt_id"]
    except Exception as e:
        console_obj.print(f"[red]Failed to queue video generation: {e}[/red]")
        return None

    # Poll /history/{prompt_id} until complete
    with console_obj.status("[cyan]Generating video...[/cyan]"):
        deadline = time.time() + 600  # 10 min timeout for video
        while time.time() < deadline:
            try:
                r = requests.get(
                    f"{COMFYUI_URL}/history/{prompt_id}",
                    timeout=5,
                )
                history = r.json()
                if prompt_id in history:
                    outputs = history[prompt_id].get("outputs", {})
                    # Find the output node with video/images
                    for node_id, node_output in outputs.items():
                        if "images" in node_output or "gifs" in node_output:
                            # Download via /view endpoint
                            items = node_output.get("gifs") or node_output.get("images", [])
                            if items:
                                return _download_comfyui_output(items[0], cfg, console_obj)
            except Exception:
                pass
            time.sleep(3)

    console_obj.print("[red]Video generation timed out.[/red]")
    return None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Long SD1.5 negative prompts (20+ terms) | Short SDXL negatives (3-5 terms) | SDXL release (2023+) | Phase 4 must differentiate; SD1.5 needs verbose negatives, SDXL needs minimal |
| ComfyUI WebSocket for live progress | HTTP polling /history is simpler for non-interactive | 2024-2025 | WebSocket adds complexity; /history polling sufficient for CLI |
| Manual SD prompt writing | LLM-crafted prompts | 2024+ | llama3.1:8b can produce high-quality SD prompts from natural language |

**Deprecated/outdated:**
- A1111 wiki API guide: Last maintained 2023-09-09; `/docs` endpoint on running instance is authoritative
- `current_image` in progress polling: Causes significant slowdown; use `skip_current_image=true`

## Open Questions

1. **ComfyUI Workflow Template for Video**
   - What we know: ComfyUI needs a full node-graph JSON, not just a prompt. The exact workflow depends on which video model is installed (CogVideoX, LTX-Video, etc.).
   - What's unclear: Which video model the user has installed. The workflow JSON must match the installed nodes.
   - Recommendation: Ship a default workflow template for the most common video model. Add a `/generate video --workflow <path>` option for custom workflows. For MVP, use a basic txt2video workflow and document which model to install.

2. **Output Directory Resolution**
   - What we know: `SD_OUTPUT_DIR` and `COMFYUI_OUTPUT_DIR` are in .env. Docker volumes map these to container paths.
   - What's unclear: Whether the host path is directly accessible for saving files, since A1111 returns base64 (so we save on host), but ComfyUI saves inside the container (need to download via /view).
   - Recommendation: For A1111: save base64 to host `SD_OUTPUT_DIR`. For ComfyUI: download via /view endpoint and save to host `COMFYUI_OUTPUT_DIR`.

3. **llama3.1:8b Availability During Generation**
   - What we know: VRAM handoff unloads models before generation. But prompt crafting needs llama3.1:8b FIRST.
   - What's unclear: If current model != llama3.1:8b, we need to swap, craft, then unload for SD.
   - Recommendation: Sequence is: save current model -> load llama3.1:8b -> craft prompt -> unload llama3.1:8b -> start generation service. The `_ensure_model_ready()` function handles the load; unload before SD start uses existing VRAM primitives.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + coverage |
| Config file | tests/conftest.py (shared fixtures) |
| Quick run command | `python -m pytest tests/unit/ -q -x --cov=clod` |
| Full suite command | `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IMG-01 | Generation intent intercepted before normal routing | unit | `python -m pytest tests/unit/test_generation.py::test_image_intent_intercepted -x` | -- Wave 0 |
| IMG-02 | llama3.1:8b crafts SD-optimized prompt from user input | unit | `python -m pytest tests/unit/test_generation.py::test_craft_sd_prompt -x` | -- Wave 0 |
| IMG-03 | Negative prompts differ by SD model type (sd15 vs sdxl) | unit | `python -m pytest tests/unit/test_generation.py::test_negative_prompts_by_model_type -x` | -- Wave 0 |
| IMG-04 | Offer to start image docker profile when A1111 not running | unit | `python -m pytest tests/unit/test_generation.py::test_offer_start_image_service -x` | -- Wave 0 |
| VID-01 | Video generation intent intercepted | unit | `python -m pytest tests/unit/test_generation.py::test_video_intent_intercepted -x` | -- Wave 0 |
| VID-02 | llama3.1:8b crafts ComfyUI-optimized prompt | unit | `python -m pytest tests/unit/test_generation.py::test_craft_video_prompt -x` | -- Wave 0 |
| VID-03 | Offer profile switch with confirmation when ComfyUI not running | unit | `python -m pytest tests/unit/test_generation.py::test_offer_profile_switch_for_video -x` | -- Wave 0 |
| DOCK-01 | Auto-detect profile switch needed based on intent + running services | unit | `python -m pytest tests/unit/test_generation.py::test_auto_detect_profile_switch -x` | -- Wave 0 |
| DOCK-02 | Confirm before profile switch with descriptive warning | unit | `python -m pytest tests/unit/test_generation.py::test_confirm_before_profile_switch -x` | -- Wave 0 |
| DOCK-03 | GPU release verification via nvidia-smi before starting new profile | unit | `python -m pytest tests/unit/test_vram.py::test_prepare_for_gpu_service_polls_vram -x` | Existing (partial) |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/ -q -x --cov=clod`
- **Per wave merge:** `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_generation.py` -- covers IMG-01 through VID-03, DOCK-01, DOCK-02
- [ ] Extend `tests/conftest.py` with `mock_generation_state` fixture (session_state with generation fields)
- [ ] Mock patterns for `requests.post` to A1111 and ComfyUI endpoints (using `responses` library)

## Sources

### Primary (HIGH confidence)
- [AUTOMATIC1111 Wiki API](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API) - txt2img payload, response format, /sdapi/v1/options
- [AUTOMATIC1111 Discussion #3734](https://github.com/AUTOMATIC1111/stable-diffusion-webui/discussions/3734) - Complete txt2img examples with base64 decoding
- [AUTOMATIC1111 Discussion #7888](https://github.com/AUTOMATIC1111/stable-diffusion-webui/discussions/7888) - Progress endpoint behavior and polling considerations
- [ComfyUI Official Routes Docs](https://docs.comfy.org/development/comfyui-server/comms_routes) - /prompt, /history, /view, /ws endpoints
- Existing codebase: `clod.py` lines 541-815 (VRAM management), 847-911 (service health), 1513-1610 (Docker switching)

### Secondary (MEDIUM confidence)
- [9elements ComfyUI API Guide](https://9elements.com/blog/hosting-a-comfyui-workflow-via-api/) - Queue + poll pattern for ComfyUI
- [Negative Prompts Guide](https://www.qwe.edu.pl/tutorial/negative-prompts-stable-diffusion/) - SD1.5 vs SDXL negative prompt differences
- [SDXL Best Practices](https://neurocanvas.net/blog/sdxl-best-practices-guide/) - SDXL needs fewer negative prompts

### Tertiary (LOW confidence)
- ComfyUI workflow JSON structure for video -- depends on installed models; needs validation against actual installed nodes

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all APIs well-documented
- Architecture: HIGH - extends existing patterns (intent interception, VRAM management, docker orchestration)
- Pitfalls: HIGH - A1111 progress polling behavior well-documented; ComfyUI workflow structure is the main risk area
- ComfyUI video workflow: LOW - depends on which video model user has installed; template may need customization

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable APIs, unlikely to change)
