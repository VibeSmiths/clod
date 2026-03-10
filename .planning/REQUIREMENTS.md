# Requirements: Clod v2 — Smart Routing & Media Generation

**Defined:** 2026-03-10
**Core Value:** When the user says what they want, clod figures out how to do it — right model, right service, right workflow — without manual switching.

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Intent Classification

- [x] **INTENT-01**: User input is classified into one of 6 intents (chat, code, reason, vision, image-gen, video-gen) before routing
- [x] **INTENT-02**: Classification completes in under 100ms without GPU usage (CPU-only via semantic-router or equivalent)
- [x] **INTENT-03**: User can override classification by using `/model` to manually select a model

### Model Routing

- [ ] **ROUTE-01**: Clod automatically selects the appropriate Ollama model based on detected intent (chat→llama3.1:8b, code→qwen2.5-coder:14b, reason→deepseek-r1:14b, vision→qwen2.5vl:7b)
- [ ] **ROUTE-02**: Before switching models, clod shows a confirmation message ("Switching to deepseek-r1:14b for reasoning...") that auto-proceeds unless user cancels
- [ ] **ROUTE-03**: Loading dialog shows Rich spinner for quick swaps (model already loaded) and progress bar for first-time pulls

### VRAM Management

- [x] **VRAM-01**: Ollama is configured with OLLAMA_MAX_LOADED_MODELS=1 to prevent OOM on 16GB GPU
- [x] **VRAM-02**: Before loading a new model, clod explicitly unloads the current model using Ollama's keep_alive:0 API
- [x] **VRAM-03**: Before switching to SD/ComfyUI, clod unloads the active Ollama model to free GPU VRAM

### Image Generation

- [ ] **IMG-01**: User can trigger image generation via natural language ("generate a picture of...", "create an image of...")
- [ ] **IMG-02**: Chat model (llama3.1:8b) crafts an SD-optimized prompt from the user's natural language description
- [ ] **IMG-03**: Default negative prompts are auto-appended based on the loaded SD model type (SD1.5 vs SDXL)
- [ ] **IMG-04**: If AUTOMATIC1111 is not running, clod offers to start the image docker profile

### Video Generation

- [ ] **VID-01**: User can trigger video generation via natural language ("make a video of...", "generate a video of...")
- [ ] **VID-02**: Chat model crafts a ComfyUI-optimized prompt from the user's natural language description
- [ ] **VID-03**: If ComfyUI is not running, clod offers to switch docker profiles (image→video) with GPU release verification

### Docker Profile Switching

- [ ] **DOCK-01**: Clod automatically detects when a docker profile switch is needed (image↔video) based on user intent
- [ ] **DOCK-02**: Before switching profiles, clod warns the user and waits for confirmation ("Switching from image to video mode, this will stop AUTOMATIC1111...")
- [ ] **DOCK-03**: Profile switch includes GPU release verification — confirms VRAM is freed before starting the new profile

### Face Swap

- [ ] **FACE-01**: User can perform single-face swap via `/faceswap <source_image> <reference_face>` slash command
- [ ] **FACE-02**: ReActor (or equivalent) runs locally, integrated with AUTOMATIC1111 or as standalone service
- [ ] **FACE-03**: Face restoration (GPEN/GFPGan) is automatically applied to swap output for quality
- [ ] **FACE-04**: User can trigger face swap via natural language ("put my face on...", "swap the face in...")
- [ ] **FACE-05**: Face swap results are displayed or saved to a user-specified path

### Offline Mode

- [x] **OFFL-01**: When in offline mode, all outbound HTTP requests are blocked (no cloud LLM calls, no web search, no external API calls)
- [x] **OFFL-02**: Offline mode is auto-detected from service health checks (LiteLLM down = no cloud) and can be manually toggled
- [x] **OFFL-03**: UI clearly indicates when offline mode is active so user knows cloud features are unavailable

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Enhanced Routing

- **ROUTE-04**: Routing confidence scores displayed in confirm UX ("Detected: reasoning, confidence: 0.87")
- **ROUTE-05**: Session intent memory — consecutive same-intent messages stay on current model without re-confirming
- **ROUTE-06**: VRAM budget dashboard showing loaded models and available headroom
- **ROUTE-07**: Fallback chain — local model fails, automatically try cloud via LiteLLM

### Enhanced Generation

- **IMG-05**: Style presets library (/style cinematic, /style anime, /style photorealistic)
- **IMG-06**: Iterative prompt refinement — "make it more dramatic" refines the SD prompt conversationally

### Enhanced Face Swap

- **FACE-06**: Named face reference storage — save face models as .safetensors, reuse by name
- **FACE-07**: Multi-face swap with face indexing ("swap face 1 with Alice, face 2 with Bob")
- **FACE-08**: PuLID/InstantID backend upgrade for higher quality (91% identity accuracy)

### GSD Integration

- **GSD-01**: Full GSD-style planning and task management inside clod's REPL

## Out of Scope

| Feature | Reason |
|---------|--------|
| Web/GUI for face swap | Clod is CLI-first; Open-WebUI exists for GUI needs |
| Video face swap | Frame-by-frame processing is 10-100x slower; defer to v2+ |
| Custom LoRA training | Requires hours of GPU time and curated datasets; outside CLI scope |
| Multi-GPU support | Single RTX 4070 Ti SUPER only; multi-GPU adds enormous complexity |
| Real-time model hot-swapping | 16GB VRAM cannot hold multiple 14b models; sequential loading only |
| Prompt marketplace | Maintenance burden and security concerns; ship good built-in presets |
| Mobile/web UI | CLI-first by design |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| VRAM-01 | Phase 1 | Complete |
| VRAM-02 | Phase 1 | Complete |
| VRAM-03 | Phase 1 | Complete |
| OFFL-01 | Phase 1 | Complete |
| OFFL-02 | Phase 1 | Complete |
| OFFL-03 | Phase 1 | Complete |
| INTENT-01 | Phase 2 | Complete |
| INTENT-02 | Phase 2 | Complete |
| INTENT-03 | Phase 2 | Complete |
| ROUTE-01 | Phase 3 | Pending |
| ROUTE-02 | Phase 3 | Pending |
| ROUTE-03 | Phase 3 | Pending |
| IMG-01 | Phase 4 | Pending |
| IMG-02 | Phase 4 | Pending |
| IMG-03 | Phase 4 | Pending |
| IMG-04 | Phase 4 | Pending |
| VID-01 | Phase 4 | Pending |
| VID-02 | Phase 4 | Pending |
| VID-03 | Phase 4 | Pending |
| DOCK-01 | Phase 4 | Pending |
| DOCK-02 | Phase 4 | Pending |
| DOCK-03 | Phase 4 | Pending |
| FACE-01 | Phase 5 | Pending |
| FACE-02 | Phase 5 | Pending |
| FACE-03 | Phase 5 | Pending |
| FACE-04 | Phase 5 | Pending |
| FACE-05 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

---
*Requirements defined: 2026-03-10*
*Last updated: 2026-03-10 after roadmap creation*
