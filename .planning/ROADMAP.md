# Roadmap: Clod v2 — Smart Routing & Media Generation

## Overview

This roadmap transforms clod from a manual-switching CLI into an intelligent router that auto-selects models and services based on user intent. The journey starts with VRAM management (the constraint everything else depends on), adds intent detection and model routing (the core value proposition), then builds natural language media generation and face swap capabilities on top of the routing infrastructure.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: VRAM Management & Offline Gating** - Safe model lifecycle and system-level feature gating (completed 2026-03-10)
- [ ] **Phase 2: Intent Classification** - CPU-based user input classification via ONNX embeddings + keyword rules
- [ ] **Phase 3: Smart Model Routing** - Auto-select and switch models with user confirmation
- [x] **Phase 4: Media Generation Pipeline** - Natural language image/video generation with docker profile orchestration (completed 2026-03-11)
- [ ] **Phase 5: Face Swap** - ReActor-based face swap with slash commands and natural language triggers

## Phase Details

### Phase 1: VRAM Management & Offline Gating
**Goal**: Clod safely manages GPU memory across model loads and generation services, and clearly gates features based on connectivity
**Depends on**: Nothing (first phase)
**Requirements**: VRAM-01, VRAM-02, VRAM-03, OFFL-01, OFFL-02, OFFL-03
**Success Criteria** (what must be TRUE):
  1. Only one Ollama model is loaded at a time -- loading a second model automatically unloads the first
  2. Before launching SD or ComfyUI, the active Ollama model is unloaded and VRAM is verified free
  3. When offline, no outbound HTTP requests are made to cloud LLMs, web search, or external APIs
  4. The UI shows a clear offline indicator when cloud features are unavailable
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — VRAM management functions (unload/verify/transition panel) + OLLAMA_MAX_LOADED_MODELS=1
- [x] 01-02-PLAN.md — Offline gating enforcement, /search toggle, UI indicators
- [x] 01-03-PLAN.md — Wire VRAM functions into /model, /gpu, and /sd handlers

### Phase 2: Intent Classification
**Goal**: User input is automatically classified by intent before any routing decision
**Depends on**: Phase 1
**Requirements**: INTENT-01, INTENT-02, INTENT-03
**Success Criteria** (what must be TRUE):
  1. Every user input is classified into one of 7 intents (chat, code, reason, vision, image-gen, image-edit, video-gen) before reaching the inference layer
  2. Classification completes in under 100ms using CPU only (no GPU, no LLM call)
  3. User can bypass classification at any time by using `/model` to manually select a model
**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md — Intent classification module (keyword rules + ONNX embedder) with model files and unit tests
- [ ] 02-02-PLAN.md — REPL integration, /intent slash command, /model override, PyInstaller spec update

### Phase 3: Smart Model Routing
**Goal**: Clod automatically picks the right Ollama model for the detected intent and switches with user visibility
**Depends on**: Phase 2
**Requirements**: ROUTE-01, ROUTE-02, ROUTE-03
**Success Criteria** (what must be TRUE):
  1. When user types a reasoning question, clod selects deepseek-r1:14b; for code, qwen2.5-coder:14b; for chat, llama3.1:8b; for vision, qwen2.5vl:7b
  2. Before switching models, a confirmation message appears ("Switching to X for Y...") that auto-proceeds unless cancelled
  3. A Rich spinner shows during quick model swaps, and a progress bar shows during first-time model pulls
**Plans**: 2 plans

Plans:
- [ ] 03-01-PLAN.md — INTENT_MODEL_MAP + _route_to_model() function + REPL wiring + routing tests
- [ ] 03-02-PLAN.md — Upgrade ollama_pull() to Rich Progress bar + spinner verification

### Phase 4: Media Generation Pipeline
**Goal**: Users generate images and videos through natural language, with automatic docker profile orchestration
**Depends on**: Phase 3
**Requirements**: IMG-01, IMG-02, IMG-03, IMG-04, VID-01, VID-02, VID-03, DOCK-01, DOCK-02, DOCK-03
**Success Criteria** (what must be TRUE):
  1. User can say "generate a picture of a sunset" and clod crafts an SD-optimized prompt via llama3.1:8b, then sends it to AUTOMATIC1111
  2. User can say "make a video of a dancing cat" and clod crafts a ComfyUI prompt and dispatches it for generation
  3. If the needed docker profile is not running, clod detects this, warns the user, and offers to switch profiles with GPU release verification
  4. Default negative prompts are automatically appended based on the active SD model type
  5. If AUTOMATIC1111 or ComfyUI is not running, clod offers to start the appropriate docker profile
**Plans**: 3 plans

Plans:
- [ ] 04-01-PLAN.md — Core image generation functions (prompt crafting, SD model detection, negative prompts, A1111 txt2img with progress)
- [ ] 04-02-PLAN.md — Video generation (ComfyUI API, workflow construction) + docker profile orchestration (auto-detect, confirm, switch)
- [ ] 04-03-PLAN.md — REPL wiring (_handle_generation_intent orchestrator, /generate slash command, intent interception)

### Phase 5: Face Swap
**Goal**: Users can perform face swaps via slash commands or natural language, powered by ReActor running locally
**Depends on**: Phase 4
**Requirements**: FACE-01, FACE-02, FACE-03, FACE-04, FACE-05
**Success Criteria** (what must be TRUE):
  1. User can run `/faceswap source.jpg reference.jpg` and get a face-swapped result
  2. ReActor runs locally integrated with AUTOMATIC1111, using approximately 260 MB VRAM on top of SD
  3. Face restoration (GPEN/GFPGan) is automatically applied to every swap output
  4. User can trigger face swap via natural language ("put my face on this photo") and clod routes it correctly
  5. Results are displayed inline or saved to a user-specified file path
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. VRAM Management & Offline Gating | 3/3 | Complete   | 2026-03-10 |
| 2. Intent Classification | 0/2 | Not started | - |
| 3. Smart Model Routing | 0/2 | Not started | - |
| 4. Media Generation Pipeline | 3/3 | Complete   | 2026-03-11 |
| 5. Face Swap | 0/2 | Not started | - |

### Phase 6: Docker Service Integration & Testing

**Goal:** [To be planned]
**Requirements**: TBD
**Depends on:** Phase 5
**Plans:** 3/3 plans complete

Plans:
- [ ] TBD (run /gsd:plan-phase 6 to break down)
