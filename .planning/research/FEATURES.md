# Feature Research

**Domain:** Local AI CLI with smart model routing, face swap/reference photo, and prompt engineering
**Researched:** 2026-03-10
**Confidence:** MEDIUM-HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist once "smart routing" and "face swap" are advertised. Missing these makes the product feel broken.

#### Smart Model Routing

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Intent classification (chat/code/reason/vision/image/video) | Core promise of "smart routing" -- without it, there is no routing | MEDIUM | Use small local LLM (llama3.1:8b or 3B classifier) to classify every prompt. Keyword fallback for reliability. Keep classifier model permanently loaded (~4-8GB). |
| Automatic model selection based on intent | Users expect the CLI to pick the right model without `/model` commands | MEDIUM | Map intents to model roster: chat->llama3.1:8b, code->qwen2.5-coder:14b, reason->deepseek-r1:14b, vision->qwen2.5vl:7b |
| Confirm-before-switch UX | Users want visibility without friction -- "Switching to deepseek-r1:14b for reasoning. [Enter/n]" | LOW | Rich inline prompt. Auto-proceed after 3s timeout. Already a project decision. |
| Fallback chain (local -> cloud) | If local model fails or is unavailable, gracefully try cloud via LiteLLM | LOW | Already partially exists via pick_adapter + LiteLLM. Formalize as explicit fallback chain with retry logic. |
| VRAM-aware model loading | Cannot load two 14b models simultaneously on 16GB GPU -- must unload first | MEDIUM | Query Ollama loaded models, estimate VRAM from model size, unload before loading. Ollama handles eviction via OLLAMA_MAX_LOADED_MODELS but explicit management is more reliable. |
| Manual override (`/model` still works) | Power users want to bypass routing when they know what they want | LOW | Already exists. Ensure routing respects explicit overrides and does not re-route after manual selection. |

#### Face Swap / Reference Photo

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single-face swap from reference photo | Core use case -- "put my face on this image" | HIGH | ReActor is the minimum viable option: fast, simple, ONNX-based. 68% identity recognition is acceptable for v1. Runs in ComfyUI as a node. |
| Face detection and indexing | Must identify which face(s) exist in source/target images | LOW | Built into ReActor and InsightFace. Left-to-right, top-to-bottom indexing is standard. |
| Face restoration / quality enhancement | Swapped faces look obviously wrong without post-processing | MEDIUM | GPEN or GFPGan restoration. ReActor has built-in restoration support. Non-negotiable for usable output. |
| Reference image management | Users need to save/load face references without re-uploading each time | LOW | ReActor supports saving face models as .safetensors files. Store in a `faces/` directory with named references. |

#### Prompt Building

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Natural language to SD prompt conversion | "Make a photo of a sunset over mountains" -> proper SD prompt with quality tags, style keywords | MEDIUM | Use llama3.1:8b with a system prompt that teaches SD prompt structure. Append standard quality tags (masterpiece, best quality, etc. for SD1.5; simpler for SDXL). |
| Automatic negative prompts | Every generation needs negative prompts -- users should not have to remember them | LOW | Ship default negative prompt sets per model type (SD1.5 vs SDXL). SDXL needs minimal negatives ("cartoon, blurry"). SD1.5 needs the standard long list. |
| Natural language generation triggers | "generate a picture of X", "make a video of Y" | MEDIUM | Intent classifier must detect image-gen and video-gen intents, then route to the prompt pipeline -> SD/ComfyUI API. |

### Differentiators (Competitive Advantage)

Features that set clod apart from other local AI CLIs and face swap tools.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Unified CLI for routing + generation + face swap | No other CLI tool combines LLM routing, image/video generation, and face swap in one interface. Users currently juggle ComfyUI browser tabs, Ollama terminal, and SD WebUI separately. | HIGH | This is the core value prop. Everything through one REPL. |
| Chat-to-prompt pipeline with iterative refinement | User describes what they want in plain English, llama3.1:8b crafts the SD prompt, shows it for approval, user can say "more dramatic lighting" and it refines. Conversational prompt engineering. | MEDIUM | Two-step: (1) classify intent as image-gen, (2) route to chat model with SD prompt system prompt, (3) pass crafted prompt to AUTOMATIC1111 API. |
| Auto docker profile switching | "Generate a video of..." automatically switches from image to video docker profile (AUTOMATIC1111 -> ComfyUI) without manual `/sd video` commands | MEDIUM | sd_switch_mode already exists. Wire it to intent classifier output. Must handle the GPU exclusivity constraint (only one GPU profile at a time). |
| Style presets library | `/style cinematic`, `/style anime`, `/style photorealistic` -- curated prompt templates with model-appropriate quality tags and negative prompts | LOW | JSON/YAML config file with preset definitions. Low effort, high usability. Ship 5-10 presets covering major styles. |
| VRAM budget dashboard | Show current VRAM usage, loaded models, and what can fit. "You have 6GB free, can load qwen2.5vl:7b but not deepseek-r1:14b" | MEDIUM | Already have query_gpu_vram. Enhance to show loaded models + available headroom. Integrate with routing decisions. |
| Multi-face swap with face indexing | "Swap face 1 with Alice, face 2 with Bob" -- swap multiple faces in one image using named references | MEDIUM | ReActor supports multi-face with index selection. Combined with named face model storage, this is powerful. |
| PuLID/InstantID upgrade path | Start with ReActor for speed, but architecture should allow upgrading to PuLID (91% identity accuracy, 10.2GB VRAM) or InstantID (84% accuracy, 8.5GB VRAM) for higher quality | HIGH | Design face swap service as an abstraction layer. ReActor first, PuLID/InstantID as optional backends. PuLID is best quality but most VRAM-hungry. |
| Routing confidence scores | Show user why a model was selected: "Detected: reasoning task (confidence: 0.87). Using deepseek-r1:14b." | LOW | Classifier outputs probabilities. Display top intent + confidence. Builds trust in routing decisions. |
| Session intent memory | Remember routing context within a conversation. If user is coding, subsequent messages default to code model without re-classifying obvious follow-ups. | MEDIUM | Track last N intents. If 3+ consecutive code intents, bias classifier toward code. Reset on explicit topic change. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Fully automatic routing (no confirmation) | "Just pick the right model, don't ask me" | Wrong classifications silently waste time. User sends a coding question, gets routed to chat model, gets bad answer, doesn't know why. Invisible failures erode trust. | Confirm-before-switch with auto-proceed timeout. User sees the decision, can override, but is not blocked. |
| Training custom face LoRAs from the CLI | "I want perfect face consistency like a trained LoRA" | LoRA training requires hours of GPU time, curated datasets, hyperparameter tuning. Way outside scope of a CLI tool. | Use pre-built ReActor/PuLID for instant face swap. Recommend external tools (kohya_ss) for users who need LoRA training. |
| Real-time model hot-swapping | "Keep all models loaded and switch instantly" | 16GB VRAM cannot hold multiple 14b models simultaneously. Attempting this causes OOM crashes or CPU offloading (unusable latency). | VRAM-aware sequential loading. Keep only the small classifier + one work model loaded. Swap takes 5-15s, which is acceptable. |
| Web/GUI for face swap | "I want a browser interface for face swap" | Duplicates Open-WebUI functionality. Adds frontend maintenance burden. Clod is CLI-first by design. | Open-WebUI already exists at localhost:3002 for GUI needs. Face swap stays CLI with file path inputs. |
| Prompt marketplace / community sharing | "Let me download and share prompt presets" | Maintenance burden, content moderation, security concerns with user-uploaded configs | Ship good built-in presets. Allow local JSON preset files that users can manually share. |
| Multi-GPU support | "I have two GPUs" | Clod targets single RTX 4070 Ti SUPER. Multi-GPU adds enormous complexity to VRAM management, model placement, and Docker GPU assignment. | Out of scope per PROJECT.md. Single-GPU optimization only. |
| Video face swap | "Swap faces in videos, not just images" | Video face swap is frame-by-frame processing that takes 10-100x longer, requires RIFE for frame interpolation, and the quality is inconsistent across frames | Defer to v2+. Start with image face swap. Video face swap is a natural extension but not MVP. |

## Feature Dependencies

```
Intent Classifier
    |
    +--requires--> Small Classifier Model (llama3.1:8b stays loaded)
    |
    +--enables--> Smart Model Routing
    |                 |
    |                 +--requires--> VRAM Management (unload before load)
    |                 |
    |                 +--requires--> Confirm-Before-Switch UX
    |                 |
    |                 +--enables--> Auto Docker Profile Switch
    |
    +--enables--> Natural Language Generation Triggers
                      |
                      +--requires--> Chat-to-Prompt Pipeline
                      |                   |
                      |                   +--requires--> SD Prompt System Prompt
                      |                   |
                      |                   +--enhances--> Style Presets
                      |
                      +--requires--> AUTOMATIC1111 / ComfyUI API Integration (exists)

Face Swap Service
    |
    +--requires--> ReActor ComfyUI Node (or standalone service)
    |
    +--requires--> InsightFace / Face Detection
    |
    +--requires--> Face Restoration (GPEN/GFPGan)
    |
    +--enhances--> Reference Image Management (named faces)
    |
    +--enhances--> Multi-Face Swap

Style Presets --enhances--> Chat-to-Prompt Pipeline
Routing Confidence --enhances--> Confirm-Before-Switch UX
Session Intent Memory --enhances--> Intent Classifier

Auto Docker Profile Switch --conflicts--> Simultaneous Image+Video
    (GPU exclusivity: only one profile active at a time)
```

### Dependency Notes

- **Intent Classifier requires small model permanently loaded:** llama3.1:8b at ~4-5GB VRAM stays resident. It classifies AND handles chat tasks. This is the "always-on" model.
- **Smart Model Routing requires VRAM Management:** Before loading deepseek-r1:14b, must confirm enough VRAM is free. May need to unload the current work model.
- **Chat-to-Prompt Pipeline requires Intent Classifier:** Must first detect that the user wants image/video generation before invoking the prompt builder.
- **Face Swap Service is independent of routing:** Can be built in parallel. Uses `/faceswap` slash command initially, then integrates with intent classifier later.
- **Auto Docker Profile Switch conflicts with simultaneous services:** AUTOMATIC1111 and ComfyUI cannot share the GPU. Switching profiles takes 10-30s for container swap.

## MVP Definition

### Launch With (v1)

Minimum viable: smart routing works, face swap works, prompt building works. Not perfect, but functional.

- [ ] **Intent classifier with 6 intents** (chat, code, reason, vision, image-gen, video-gen) -- the foundation everything else builds on
- [ ] **Automatic model selection with confirm-before-switch** -- core value prop of "clod figures it out"
- [ ] **VRAM-aware model loading** -- without this, model switches crash or degrade to CPU
- [ ] **Fallback chain (local -> cloud)** -- graceful degradation when local model unavailable
- [ ] **ReActor face swap via `/faceswap`** -- slash command with source image + reference face
- [ ] **Face restoration on swap output** -- GPEN/GFPGan, otherwise output is unusable
- [ ] **Chat-to-prompt pipeline** -- llama3.1:8b converts natural language to SD prompts
- [ ] **Default negative prompts** -- auto-appended per model type (SD1.5 vs SDXL)
- [ ] **Natural language generation triggers** -- "generate an image of..." detected and routed

### Add After Validation (v1.x)

Features to add once core routing and face swap are proven.

- [ ] **Style presets library** -- add when users start asking "how do I get cinematic style"
- [ ] **Auto docker profile switching** -- add after manual routing is stable
- [ ] **Multi-face swap** -- add after single-face swap is reliable
- [ ] **Named face reference storage** -- add after users start re-using the same faces
- [ ] **Routing confidence scores in UI** -- add when users question routing decisions
- [ ] **Session intent memory** -- add when users complain about redundant model switches in conversations
- [ ] **VRAM budget dashboard** -- add when users want to understand why a model was not selected

### Future Consideration (v2+)

- [ ] **PuLID/InstantID backend** -- higher quality face swap, but 10+ GB VRAM. Defer until ReActor proves the workflow, then upgrade the backend.
- [ ] **Video face swap** -- frame-by-frame processing with RIFE interpolation. High complexity, defer until image face swap is mature.
- [ ] **Iterative prompt refinement** -- "make it more dramatic" -> refine the SD prompt conversationally. Needs good UX design.
- [ ] **GSD-style planning inside clod** -- task tracking in the REPL. Large feature, orthogonal to routing/generation.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Intent classifier (6 intents) | HIGH | MEDIUM | P1 |
| Auto model selection + confirm UX | HIGH | MEDIUM | P1 |
| VRAM-aware model loading | HIGH | MEDIUM | P1 |
| Fallback chain (local -> cloud) | MEDIUM | LOW | P1 |
| ReActor face swap (`/faceswap`) | HIGH | HIGH | P1 |
| Face restoration (GPEN) | HIGH | LOW | P1 |
| Chat-to-prompt pipeline | HIGH | MEDIUM | P1 |
| Default negative prompts | MEDIUM | LOW | P1 |
| NL generation triggers | HIGH | MEDIUM | P1 |
| Style presets | MEDIUM | LOW | P2 |
| Auto docker profile switch | MEDIUM | MEDIUM | P2 |
| Multi-face swap | MEDIUM | MEDIUM | P2 |
| Named face references | MEDIUM | LOW | P2 |
| Routing confidence display | LOW | LOW | P2 |
| Session intent memory | MEDIUM | MEDIUM | P2 |
| VRAM dashboard | LOW | MEDIUM | P2 |
| PuLID/InstantID upgrade | MEDIUM | HIGH | P3 |
| Video face swap | MEDIUM | HIGH | P3 |
| Iterative prompt refinement | MEDIUM | MEDIUM | P3 |
| GSD planning in REPL | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch -- routing, face swap, and prompt pipeline core
- P2: Should have, add when P1 is stable
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature | Ollama CLI | Open-WebUI | ComfyUI (browser) | LM Studio | Clod (our approach) |
|---------|-----------|------------|-------------------|-----------|-------------------|
| Model routing | Manual only | Manual dropdown | N/A (workflow-based) | Manual only | Auto-classify + confirm-before-switch |
| Face swap | None | None | Full workflow (ReActor, PuLID, InstantID nodes) | None | CLI-driven, ReActor first, upgrade path to PuLID |
| Image generation | None | SD integration | Full workflow | None | NL triggers -> chat-to-prompt -> AUTOMATIC1111 |
| Video generation | None | None | Full workflow | None | NL triggers -> ComfyUI API |
| Prompt engineering | None | None | Manual node config | None | LLM-assisted prompt building with style presets |
| VRAM management | Auto-eviction | None | Manual | Shows VRAM usage | VRAM-aware routing with budget display |
| Fallback (local->cloud) | None | Can add cloud models | None | Cloud API support | Automatic fallback chain via LiteLLM |
| Unified interface | Terminal only | Browser only | Browser only | Desktop app | Single CLI/REPL for everything |

**Key insight:** ComfyUI has the most powerful face swap ecosystem but requires browser-based node editing. No existing tool offers CLI-driven face swap with LLM routing. This is clod's unique position -- bringing ComfyUI's power into a terminal workflow.

## Sources

- [NVIDIA LLM Router Blueprint](https://github.com/NVIDIA-AI-Blueprints/llm-router) - model routing architecture patterns
- [LiteLLM Auto Routing docs](https://docs.litellm.ai/docs/proxy/auto_routing) - proxy-level routing (already in clod's stack)
- [Model Router with Ollama and LiteLLM](https://medium.com/@michael.hannecke/implementing-llm-model-routing-a-practical-guide-with-ollama-and-litellm-b62c1562f50f) - practical local routing guide
- [llama.cpp Model Router](https://huggingface.co/blog/ggml-org/model-management-in-llamacpp) - native model management (Dec 2025)
- [ComfyUI-ReActor](https://github.com/Gourieff/ComfyUI-ReActor) - face swap node for ComfyUI
- [PuLID vs InstantID vs FaceID comparison](https://myaiforce.com/pulid-vs-instantid-vs-faceid/) - quality/VRAM benchmarks
- [Face swap comparison (4 techniques)](https://myaiforce.com/hyperlora-vs-instantid-vs-pulid-vs-ace-plus/) - 2025 comparison
- [ComfyUI InstantID](https://github.com/cubiq/ComfyUI_InstantID) - alternative face swap backend
- [IP-Adapter](https://github.com/tencent-ailab/IP-Adapter) - image prompt adapter for style transfer
- [SD Negative Prompts Guide](https://freeaipromptmaker.com/blog/2025-11-29-stable-diffusion-negative-prompts-guide) - negative prompt best practices
- [LLM-grounded Diffusion](https://llm-grounded-diffusion.github.io/) - LLM-to-diffusion prompt pipeline research
- [Local LLM for SD Prompts](https://www.arsturn.com/blog/create-better-ai-art-how-to-use-a-local-llm-to-generate-stable-diffusion-prompts) - practical prompt generation

---
*Feature research for: Local AI CLI with smart routing, face swap, and prompt engineering*
*Researched: 2026-03-10*
