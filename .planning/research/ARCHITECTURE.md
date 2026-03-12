# Architecture Patterns

**Domain:** Local AI CLI with smart routing and media generation
**Researched:** 2026-03-10

## Recommended Architecture

The existing single-file architecture (`clod.py`, ~2776 lines) needs to be extended with four new subsystems: intent classification, model management, face swap orchestration, and a modular extraction layer. These integrate at well-defined points in the existing code without rewriting the core.

### High-Level Component Map

```
User Input
    |
    v
[REPL Loop]  (run_repl, lines 2537-2639)
    |
    +-- Slash command? --> [Command Router] (handle_slash)
    |
    +-- Natural language --> [Intent Classifier] (NEW)
            |
            +-- chat/code/reason --> [Model Router] (NEW) --> pick_adapter --> infer()
            |
            +-- image-gen --> [Prompt Crafter] (NEW) --> AUTOMATIC1111 API
            |
            +-- video-gen --> [Prompt Crafter] (NEW) --> sd_switch_mode --> ComfyUI API
            |
            +-- face-swap --> [Face Swap Orchestrator] (NEW) --> ReActor API
            |
            +-- vision --> [Model Router] --> pick_adapter(qwen2.5vl:7b) --> infer()
```

### Component Boundaries

| Component | Responsibility | Communicates With | Location |
|-----------|---------------|-------------------|----------|
| Intent Classifier | Classify user input into intent categories | REPL loop (input), Model Router (output) | `clod_intent.py` (new module) |
| Model Router | Select Ollama model based on intent, manage VRAM | Intent Classifier (input), Ollama API (load/unload), session_state (mutations) | `clod_routing.py` (new module) |
| Prompt Crafter | Convert natural language into SD/ComfyUI prompts via llama3.1:8b | Model Router (trigger), Ollama API (inference), SD/ComfyUI APIs (output) | `clod_media.py` (new module) |
| Face Swap Orchestrator | Coordinate face swap pipeline: reference photo + target generation | REPL loop (trigger), AUTOMATIC1111 + ReActor API (execution) | `clod_media.py` (same module as Prompt Crafter) |
| VRAM Manager | Track loaded models, unload before loading, enforce 16 GB ceiling | Model Router (queries), Ollama API (`/api/ps`, `/api/generate` with keep_alive=0) | `clod_routing.py` (same module as Model Router) |

### New Module Structure (PyInstaller-Compatible)

```
clod/
  clod.py              # Main CLI (existing, becomes thinner dispatcher)
  clod_intent.py       # Intent classification (rule-based + optional LLM)
  clod_routing.py      # Model selection, VRAM management, hot-swap
  clod_media.py        # Media generation: prompt crafting, face swap, SD/ComfyUI API
  mcp_server.py        # MCP filesystem server (existing, unchanged)
```

**PyInstaller integration:** Add all new modules to `hiddenimports` in `clod.spec` and use explicit `import clod_intent, clod_routing, clod_media` at the top of `clod.py`. PyInstaller traces static imports reliably; no dynamic `importlib` needed. The `collect_submodules` hook function is unnecessary for a flat module structure.

## Data Flow

### Intent-Driven Inference Turn (New Flow)

```
1. User submits message in REPL
2. If starts with "/" --> existing handle_slash() (unchanged)
3. Otherwise --> classify_intent(user_input)
4.   Intent classifier returns: {
5.     "intent": "code" | "chat" | "reason" | "vision" | "image_gen" | "video_gen" | "face_swap",
6.     "confidence": 0.0-1.0,
7.     "extracted": { ... }  # e.g., {"prompt": "a cat on mars"} for image_gen
8.   }
9.
10. If intent is chat/code/reason/vision:
11.   a. Model Router resolves target model from INTENT_MODEL_MAP
12.   b. If target != currently loaded model:
13.       - Show confirmation: "Switching to deepseek-r1:14b for reasoning... [Y/n]"
14.       - If confirmed: VRAM Manager unloads current, loads target
15.       - Update session_state["model"]
16.   c. Proceed to infer() as normal
17.
18. If intent is image_gen or video_gen:
19.   a. Ensure correct Docker profile (sd_switch_mode if needed)
20.   b. Feed user input to Prompt Crafter (llama3.1:8b generates SD prompt)
21.   c. POST to AUTOMATIC1111/ComfyUI API with crafted prompt
22.   d. Display result path/panel in Rich UI
23.
24. If intent is face_swap:
25.   a. Prompt for reference photo path (if not provided in input)
26.   b. Ensure AUTOMATIC1111 profile running with ReActor extension
27.   c. Generate base image via txt2img or img2img
28.   d. Apply face swap via ReActor alwayson_scripts
29.   e. Display result
```

### VRAM Management Flow

```
1. Model Router decides target model (e.g., deepseek-r1:14b)
2. Query Ollama: GET /api/ps --> list currently loaded models + VRAM usage
3. If target already loaded --> skip, proceed to infer
4. If different model loaded:
   a. POST /api/generate {"model": "<current>", "keep_alive": 0} --> unload
   b. Wait for unload confirmation (done_reason: "unload")
   c. POST /api/generate {"model": "<target>", "keep_alive": "10m"} --> preload
   d. Show Rich spinner during load, progress bar if first-time pull
5. Update session_state["model"] = target
```

### Face Swap Pipeline Flow

```
1. User: "put my face on a superhero"
2. Intent: face_swap, extracted: {"scene": "superhero", "ref_photo": null}
3. If no ref_photo cached:
   a. Prompt: "Path to reference face photo: "
   b. Validate file exists, cache path in session_state["ref_photo"]
4. Prompt Crafter: llama3.1:8b generates SD prompt from "superhero"
   --> e.g., "a muscular superhero in a cape, full body, detailed face, 8k"
5. POST to AUTOMATIC1111 /sdapi/v1/txt2img with:
   - prompt, negative_prompt, steps, cfg_scale, width, height
   - "alwayson_scripts": {
       "reactor": {
         "args": [
           base64(ref_photo),   # source face image
           true,                # enable
           "0",                 # source face index
           "0",                 # target face index
           "inswapper_128.onnx", # model
           "CodeFormer",        # face restorer
           1,                   # restorer visibility
           true,                # restore face
           ...                  # gender detection, etc.
         ]
       }
     }
6. Decode base64 response image, save to output dir
7. Display file path + image info panel in Rich UI
```

## Patterns to Follow

### Pattern 1: Intent Classification (Tiered Rule + LLM)

**What:** Two-tier classification -- fast regex/keyword rules first, LLM fallback for ambiguous inputs.
**When:** Every non-slash user input in the REPL loop.
**Why:** Rule-based handles 80%+ of inputs with zero latency. LLM fallback (using the already-loaded model) handles edge cases without adding a new dependency or VRAM pressure.

```python
# clod_intent.py

import re
from typing import Optional

# Intent categories
INTENTS = ("chat", "code", "reason", "vision", "image_gen", "video_gen", "face_swap")

# Tier 1: Keyword/regex rules (fast, no model needed)
_RULES = [
    # image generation
    (r"\b(generate|create|make|draw|paint)\b.+\b(image|picture|photo|illustration|art)\b", "image_gen"),
    (r"\b(generate|create|make)\b.+\b(video|animation|clip)\b", "video_gen"),
    (r"\b(face\s*swap|put my face|swap.+face|my face on)\b", "face_swap"),
    # reasoning triggers
    (r"\b(explain|why|how does|analyze|think.+through|step.+by.+step|reason)\b", "reason"),
    # code triggers
    (r"\b(write|code|function|class|implement|debug|refactor|fix.+bug|snippet)\b", "code"),
    # vision (file reference with image extension)
    (r"\.(png|jpg|jpeg|gif|webp|bmp)\b", "vision"),
]

def classify_intent(user_input: str, llm_fallback=None) -> dict:
    """Classify user intent. Returns {"intent": str, "confidence": float, "extracted": dict}."""
    text = user_input.lower().strip()

    # Tier 1: Rule-based
    for pattern, intent in _RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return {"intent": intent, "confidence": 0.85, "extracted": {}}

    # Tier 2: LLM classification (optional, uses current model)
    if llm_fallback:
        return llm_fallback(user_input)

    # Default: chat
    return {"intent": "chat", "confidence": 0.5, "extracted": {}}
```

### Pattern 2: VRAM-Aware Model Router

**What:** Map intents to models, manage VRAM budget via Ollama API.
**When:** After intent classification resolves to a text-inference intent.
**Why:** 16 GB VRAM means only one 14b model at a time. Must unload before loading.

```python
# clod_routing.py

import requests
from typing import Optional

INTENT_MODEL_MAP = {
    "code":      "qwen2.5-coder:14b",
    "reason":    "deepseek-r1:14b",
    "vision":    "qwen2.5vl:7b",
    "chat":      "llama3.1:8b",
    "image_gen": "llama3.1:8b",   # used for prompt crafting only
    "video_gen": "llama3.1:8b",   # used for prompt crafting only
    "face_swap": "llama3.1:8b",   # used for prompt crafting only
}

def get_loaded_models(ollama_url: str) -> list[dict]:
    """Query Ollama /api/ps for currently loaded models."""
    try:
        r = requests.get(f"{ollama_url}/api/ps", timeout=5)
        return r.json().get("models", [])
    except Exception:
        return []

def unload_model(model_name: str, ollama_url: str) -> bool:
    """Unload a model by sending keep_alive=0."""
    try:
        r = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": model_name, "keep_alive": 0},
            timeout=30,
        )
        return r.status_code == 200
    except Exception:
        return False

def ensure_model_loaded(target: str, ollama_url: str) -> bool:
    """Unload other models if needed, then preload target."""
    loaded = get_loaded_models(ollama_url)
    loaded_names = [m["name"] for m in loaded]

    if target in loaded_names:
        return True  # already loaded

    # Unload all currently loaded models to free VRAM
    for m in loaded:
        unload_model(m["name"], ollama_url)

    # Preload target (empty prompt, keep_alive="10m")
    try:
        r = requests.post(
            f"{ollama_url}/api/generate",
            json={"model": target, "keep_alive": "10m", "prompt": ""},
            timeout=120,
        )
        return r.status_code == 200
    except Exception:
        return False
```

### Pattern 3: Confirm-Before-Switch UX

**What:** Show user what model switch is happening, let them override.
**When:** Intent classifier wants a different model than currently loaded.
**Why:** Users want visibility without friction. Default is YES (just press Enter).

```python
# Integration point in REPL loop (clod.py lines ~2621-2636)

def _maybe_switch_model(intent_result, session_state, cfg, console):
    """Check if model switch needed, confirm with user, execute swap."""
    target = INTENT_MODEL_MAP.get(intent_result["intent"], cfg["default_model"])
    current = session_state["model"]

    if target == current:
        return  # no switch needed

    # Show confirmation
    label = intent_result["intent"].replace("_", " ")
    console.print(
        f"[dim]Detected [bold]{label}[/bold] intent "
        f"-- switching to [bold]{target}[/bold]...[/dim]"
    )

    # Non-blocking confirm (default yes, timeout or Enter = proceed)
    # For now: auto-proceed with 1-second display delay
    # Future: add [Y/n] prompt for explicit override

    ensure_model_loaded(target, cfg["ollama_url"])
    session_state["model"] = target
```

### Pattern 4: ReActor Integration via AUTOMATIC1111 API

**What:** Face swap via the ReActor extension's alwayson_scripts API.
**When:** Intent is face_swap and AUTOMATIC1111 is running with ReActor installed.
**Why:** ReActor hooks into the existing txt2img/img2img pipeline -- no separate service needed.

```python
# clod_media.py (face swap portion)

import base64
import requests

def face_swap_generate(
    prompt: str,
    ref_photo_path: str,
    sd_url: str = "http://localhost:7860",
    steps: int = 30,
    width: int = 512,
    height: int = 768,
) -> bytes:
    """Generate image with face swap via ReActor alwayson_scripts."""
    with open(ref_photo_path, "rb") as f:
        ref_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "prompt": prompt,
        "negative_prompt": "blurry, distorted face, extra limbs",
        "steps": steps,
        "width": width,
        "height": height,
        "cfg_scale": 7,
        "alwayson_scripts": {
            "reactor": {
                "args": [
                    ref_b64,              # 0: source image (base64)
                    True,                 # 1: enable ReActor
                    "0",                  # 2: source face index
                    "0",                  # 3: target face index
                    "inswapper_128.onnx", # 4: face swap model
                    "CodeFormer",         # 5: face restorer name
                    1,                    # 6: restorer visibility
                    True,                 # 7: restore face after swap
                    1,                    # 8: postprocessing order
                    1,                    # 9: face restorer scale
                    1,                    # 10: face detection model (retinaface)
                    False,                # 11: gender detection
                    False,                # 12: save output
                ]
            }
        },
    }
    r = requests.post(f"{sd_url}/sdapi/v1/txt2img", json=payload, timeout=300)
    r.raise_for_status()
    img_b64 = r.json()["images"][0]
    return base64.b64decode(img_b64)
```

## Anti-Patterns to Avoid

### Anti-Pattern 1: Loading Two 14b Models Simultaneously

**What:** Attempting to keep multiple large models in VRAM for faster switching.
**Why bad:** RTX 4070 Ti SUPER has 16 GB. A single 14b model uses 9-10 GB. Two models = OOM, Ollama will silently fall back to CPU inference (extremely slow) or crash.
**Instead:** Always unload current model before loading a new one via `keep_alive: 0`. Accept the 5-15 second swap latency.

### Anti-Pattern 2: LLM-Only Intent Classification

**What:** Sending every user input through an LLM to classify intent before responding.
**Why bad:** Adds 2-5 seconds latency per turn. Requires a model to be loaded just for classification. Wastes VRAM on a chat model when user wants code generation.
**Instead:** Use regex/keyword rules as Tier 1 (zero latency). LLM fallback only for genuinely ambiguous inputs, and only using the already-loaded model (no extra model load).

### Anti-Pattern 3: Running ReActor as Separate Docker Service

**What:** Deploying a standalone face swap container separate from AUTOMATIC1111.
**Why bad:** ReActor is designed as an A1111 extension. Separate deployment means reimplementing the entire InsightFace/ONNX pipeline, managing a second GPU-using container, and coordinating two services for one operation.
**Instead:** Install ReActor as an extension inside the existing stable-diffusion container. Use its alwayson_scripts API integration.

### Anti-Pattern 4: Converting clod.py to a Package with __init__.py

**What:** Restructuring into `clod/` package with subpackages.
**Why bad:** Breaks the existing PyInstaller spec, import paths, test fixtures, and CI/CD pipeline. Massive refactor for marginal benefit.
**Instead:** Extract to sibling modules (`clod_intent.py`, `clod_routing.py`, `clod_media.py`) at the same directory level. Add to `hiddenimports` in `clod.spec`. Existing `clod.py` imports them at the top -- PyInstaller traces these cleanly.

### Anti-Pattern 5: Stateless Model Router

**What:** Re-classifying intent and potentially switching models on every single message, including follow-ups in the same conversation.
**Why bad:** User asks a code question, gets a response, then says "can you also add error handling?" -- this is still a code intent but might be misclassified as chat. Constant model switching is disruptive and slow.
**Instead:** Sticky model selection. Once a model is selected for a conversation thread, it stays unless the user explicitly triggers a new intent category or uses `/model` to switch manually. Reset on `/clear`.

## Integration Points with Existing Code

### 1. REPL Loop (clod.py lines 2608-2639)

The intent classifier inserts between user input and `infer()`. Current flow:

```python
# CURRENT (lines 2621-2636):
if user_input.startswith("/"):
    handle_slash(...)
    continue
messages.append({"role": "user", "content": user_input})
reply = infer(messages, session_state["model"], ...)
```

Becomes:

```python
# NEW:
if user_input.startswith("/"):
    handle_slash(...)
    continue

intent = classify_intent(user_input)
_maybe_switch_model(intent, session_state, cfg, console)

if intent["intent"] in ("image_gen", "video_gen", "face_swap"):
    handle_media_intent(intent, user_input, session_state, cfg, console)
    continue

messages.append({"role": "user", "content": user_input})
reply = infer(messages, session_state["model"], ...)
```

### 2. pick_adapter (clod.py line 1462)

No changes needed. The Model Router changes `session_state["model"]` before `infer()` calls `pick_adapter()`. The adapter pattern still works because the model name determines the backend.

### 3. sd_switch_mode (clod.py line 1210)

Called automatically by the media intent handler when Docker profile needs switching (e.g., image_gen needs AUTOMATIC1111, video_gen needs ComfyUI). Existing function is already correct -- just needs to be invoked programmatically instead of only via `/sd mode`.

### 4. session_state (clod.py line 2552)

New keys added to session_state dict:

```python
session_state = {
    # ... existing keys ...
    "ref_photo": None,           # cached face reference photo path
    "intent_sticky": None,       # sticky intent to avoid flip-flopping
    "auto_route": True,          # enable/disable intent-based routing
}
```

### 5. Slash Commands (handle_slash)

New commands added:

| Command | Action |
|---------|--------|
| `/autoroute` or `/auto` | Toggle intent-based model routing on/off |
| `/faceswap [path]` | Explicit face swap with optional reference photo |
| `/generate image [prompt]` | Explicit image generation |
| `/generate video [prompt]` | Explicit video generation |
| `/ref [path]` | Set/show current reference face photo |

## Suggested Build Order

Build order follows dependency chains. Each phase produces a testable, usable increment.

### Phase 1: Module Extraction + VRAM Manager

**Dependencies:** None (refactoring only)
**Delivers:** `clod_routing.py` with VRAM management, `clod_intent.py` stub

1. Extract `INTENT_MODEL_MAP` and VRAM management functions into `clod_routing.py`
2. Implement `get_loaded_models()`, `unload_model()`, `ensure_model_loaded()`
3. Create `clod_intent.py` with rule-based classifier
4. Update `clod.spec` hiddenimports
5. Verify PyInstaller build still works
6. Add unit tests for classifier and VRAM manager (mock Ollama API)

**Why first:** This is the foundation. Everything else depends on intent classification and model management. Pure refactor with no UX changes means low risk.

### Phase 2: Intent-Driven Model Routing

**Dependencies:** Phase 1 (intent classifier + VRAM manager)
**Delivers:** Auto-switching models based on user input

1. Wire `classify_intent()` into REPL loop (between input and `infer()`)
2. Implement `_maybe_switch_model()` with confirm-before-switch UX
3. Add sticky intent logic (don't flip-flop on follow-up messages)
4. Add `/autoroute` toggle command
5. Add Rich loading UI (spinner for model swap, progress bar for pulls)

**Why second:** Highest user-visible value. Once this works, every text interaction benefits from smart routing. No Docker dependency changes.

### Phase 3: Prompt Crafting + Image/Video Generation

**Dependencies:** Phase 2 (intent classifier routes to image_gen/video_gen)
**Delivers:** Natural language triggers for image and video generation

1. Create `clod_media.py` with prompt crafting function
2. Implement chat-to-prompt pipeline (llama3.1:8b rewrites user input as SD prompt)
3. Wire image_gen intent to AUTOMATIC1111 txt2img API
4. Wire video_gen intent to auto-profile-switch + ComfyUI API
5. Add `/generate` slash commands as explicit fallback
6. Handle Docker profile switching automatically

**Why third:** Builds on intent classification. Requires prompt crafting (model routing) and Docker profile switching (existing sd_switch_mode). No new Docker services needed.

### Phase 4: Face Swap Integration

**Dependencies:** Phase 3 (media pipeline), ReActor extension in SD container
**Delivers:** Face swap via natural language or /faceswap command

1. Add ReActor extension to stable-diffusion Docker image (or Dockerfile)
2. Implement face swap orchestrator in `clod_media.py`
3. Add reference photo caching in session_state
4. Wire face_swap intent through the pipeline
5. Add `/faceswap` and `/ref` slash commands
6. Add image display/save handling

**Why last:** Requires ReActor extension installed in AUTOMATIC1111 container (infrastructure change). Depends on the media pipeline from Phase 3. Highest complexity, most unknowns (ReActor model downloads, ONNX runtime in container).

## Scalability Considerations

| Concern | Current (Single User) | If Adding Web UI Later |
|---------|----------------------|----------------------|
| VRAM contention | Single REPL controls model loading exclusively | Need model lease/lock mechanism |
| Docker profile switching | Blocks REPL during switch (acceptable) | Would need async job queue |
| Face swap latency | 30-60s acceptable in CLI | Would need progress websocket |
| Intent classification | Rule-based in-process (instant) | Same rules work server-side |
| Session state | In-memory dict (single process) | Would need Redis/file persistence |

## Sources

- [Ollama API documentation](https://github.com/ollama/ollama/blob/main/docs/api.md) - Model loading, unloading, keep_alive parameter (HIGH confidence)
- [Ollama FAQ - VRAM management](https://docs.ollama.com/faq) - OLLAMA_MAX_LOADED_MODELS, default keep_alive behavior (HIGH confidence)
- [ReActor face swap extension](https://github.com/Gourieff/sd-webui-reactor) - A1111 extension for face swapping (HIGH confidence)
- [ReActor API documentation](https://github.com/Gourieff/sd-webui-reactor-sfw/blob/main/API.md) - alwayson_scripts integration format (MEDIUM confidence -- 429 on fetch, verified via multiple tutorials)
- [ComfyUI ReActor node](https://github.com/Gourieff/ComfyUI-ReActor) - ComfyUI face swap alternative (MEDIUM confidence)
- [PyInstaller hooks documentation](https://pyinstaller.org/en/stable/hooks.html) - hiddenimports, collect_submodules for multi-module bundling (HIGH confidence)
- [Unloading Ollama models](https://pauleasterbrooks.com/articles/technology/clearing-ollama-memory) - Practical keep_alive=0 usage (MEDIUM confidence)
- [ComfyUI InstantID face swap](https://github.com/nosiu/comfyui-instantId-faceswap) - Alternative face swap for ComfyUI workflows (MEDIUM confidence)

---

*Architecture research: 2026-03-10*
