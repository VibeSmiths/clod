# Clod — Local AI CLI with Smart Routing & Media Generation

## What This Is

Clod is a local AI CLI that talks to Ollama models, with Docker-managed services for search, image generation, and automation. It intelligently routes user input to the right model based on detected intent, generates images and videos through natural language, and orchestrates GPU memory across services — all without manual switching.

## Core Value

When the user says what they want, clod figures out how to do it — right model, right service, right workflow — without manual switching.

## Requirements

### Validated

- ✓ Ollama inference with streaming — existing
- ✓ LiteLLM cloud model fallback (Claude/GPT) — existing
- ✓ Docker service management (start/stop/reset) — existing
- ✓ SD image generation via AUTOMATIC1111 — existing
- ✓ Video generation via ComfyUI — existing
- ✓ sd_switch_mode between image/video profiles — existing
- ✓ Tool execution (bash, file I/O, web search) — existing
- ✓ Rich TUI with streaming panels — existing
- ✓ `/model` manual model switching — existing
- ✓ Service health checks and auto-restore — existing
- ✓ Intent detection — 7-intent CPU classification (keyword + ONNX) — v1.0
- ✓ Smart model routing — auto-select Ollama model based on detected intent — v1.0
- ✓ Confirm-before-switch UX — "Switching to X for Y..." auto-proceed — v1.0
- ✓ Loading dialog — Rich spinner for swaps, progress bar for pulls — v1.0
- ✓ Chat-to-prompt pipeline — llama3.1:8b crafts SD/ComfyUI prompts — v1.0
- ✓ Auto docker profile switch — swap image/video profiles on intent — v1.0
- ✓ Natural language generation — "generate a picture of...", "make a video of..." — v1.0
- ✓ VRAM lifecycle management — safe model unloading, GPU memory verification — v1.0
- ✓ Offline gating — auto-detect connectivity, block cloud calls — v1.0
- ✓ /generate slash command — explicit image/video generation fallback — v1.0

### Active

- [ ] Face swap / reference photo service — split to separate project (ReActor + AUTOMATIC1111)
- [ ] GSD-style planning inside clod — task tracking, project management in REPL

### Out of Scope

- Mobile/web UI — clod stays CLI-first
- Training/fine-tuning models — use pre-trained models only
- Real-time video streaming — batch generation only
- Multi-GPU support — single RTX 4070 Ti SUPER (16 GB VRAM)
- Video face swap — frame-by-frame processing too slow for CLI

## Context

**Shipped v1.0** with 3,994 LOC Python (clod.py 3,745 + intent.py 249), 498 unit tests at 91% coverage.

**Hardware constraint:** RTX 4070 Ti SUPER with 16 GB VRAM. 14b is the practical ceiling for local inference.

**Model map:**
- Default/Code: `qwen2.5-coder:14b`
- Reason: `deepseek-r1:14b`
- Vision: `qwen2.5vl:7b`
- Chat: `llama3.1:8b`
- Cloud fallback: Claude API via LiteLLM

**Docker services:** Ollama, Open-WebUI, SearXNG, n8n, ChromaDB, AUTOMATIC1111 (7860), ComfyUI (8188). Image and video are separate docker-compose profiles.

**Architecture:** Single-file CLI (`clod.py`) with adapter pattern for inference backends, intent classification module (`intent.py`), streaming event protocol, and tool execution loop. Smart routing auto-selects models based on intent. Generation pipeline handles VRAM handoffs between LLM and GPU services.

## Constraints

- **VRAM**: 16 GB max — model routing must unload before loading different-sized models
- **Docker profiles**: image (AUTOMATIC1111) and video (ComfyUI) are mutually exclusive GPU profiles
- **Single file**: clod.py is 3,745 lines — future features may need module extraction
- **PyInstaller**: any new dependencies must be bundleable into the Windows EXE

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Confirm-before-switch (not full auto) | User wants visibility into routing decisions without friction | ✓ Good — cyan "Switching to X for Y..." message |
| Natural language + slash commands | NL for convenience, slash commands as reliable fallback | ✓ Good — both paths work |
| Chat model crafts SD prompts | llama3.1:8b is lightweight, good at conversational prompt building | ✓ Good — single-shot crafting |
| OLLAMA_MAX_LOADED_MODELS=1 | Prevent OOM on 16 GB GPU | ✓ Good — env var in docker-compose |
| ONNX UINT8/AVX2 for intent | CPU-only, <100ms, no GPU needed | ✓ Good — keyword fast path + embedding fallback |
| try/finally for model restore | Ensure model reload even on generation failure | ✓ Good — prevents orphaned GPU state |
| Face swap split to separate project | Phase 5 never started, defers complexity | — User decision at milestone completion |

---
*Last updated: 2026-03-11 after v1.0 milestone*
