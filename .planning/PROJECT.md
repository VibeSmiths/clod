# Clod v2 — Smart Routing & Media Generation

## What This Is

Clod is a local AI CLI that talks to Ollama models, with Docker-managed services for search, image generation, and automation. This milestone evolves clod from a manual-switching CLI into an intelligent router that detects user intent, auto-selects the right model/service, and adds reference-photo capabilities (face swap, style transfer, scene compositing) — all orchestrated through natural language or explicit commands.

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

### Active

- [ ] Intent detection — classify user input as chat/code/reason/vision/image-gen/video-gen/face-swap
- [ ] Smart model routing — auto-select Ollama model based on detected intent
- [ ] Confirm-before-switch UX — "Switching to deepseek-r1:14b for reasoning..." with option to override
- [ ] Loading dialog — Rich spinner for quick model swaps, progress bar for first-time pulls
- [ ] Chat-to-prompt pipeline — use llama3.1:8b to craft SD/ComfyUI prompts before generation
- [ ] Auto docker profile switch — swap between image/video docker profiles based on intent
- [ ] Face swap / reference photo service — local service for face swap, scene compositing, style transfer
- [ ] Natural language generation triggers — "generate a picture of...", "make a video of...", "put my face on..."
- [ ] Slash command fallback — /faceswap, /generate image, /generate video as explicit alternatives
- [ ] GSD-style planning inside clod — task tracking, step-by-step execution, project management in REPL

### Out of Scope

- Mobile/web UI — clod stays CLI-first
- Training/fine-tuning models — use pre-trained models only
- Real-time video streaming — batch generation only
- Multi-GPU support — single RTX 4070 Ti SUPER (16 GB VRAM)

## Context

**Hardware constraint:** RTX 4070 Ti SUPER with 16 GB VRAM. The 32b model exceeds this; 14b is the practical ceiling for local inference. Model routing must be VRAM-aware — can't have two large models loaded simultaneously.

**Existing model map (from CLAUDE.md):**
- Default/Code: `qwen2.5-coder:14b`
- Reason: `deepseek-r1:14b`
- Vision: `qwen2.5vl:7b`
- Chat: `llama3.1:8b`
- Cloud fallback: Claude API via LiteLLM

**Existing Docker services:** Ollama, Open-WebUI, SearXNG, n8n, ChromaDB, AUTOMATIC1111 (port 7860), ComfyUI (port 8188). Image and video are separate docker-compose profiles.

**Face swap / reference photo:** Needs research — ReActor, IP-Adapter, InstantID, or similar. Must run locally, integrate with existing SD infrastructure or as new Docker service.

**Current architecture:** Single-file CLI (`clod.py`, ~2776 lines) with adapter pattern for inference backends, streaming event protocol, and tool execution loop. Model selection is currently manual via `/model` command.

## Constraints

- **VRAM**: 16 GB max — model routing must unload before loading different-sized models
- **Docker profiles**: image (AUTOMATIC1111) and video (ComfyUI) are mutually exclusive GPU profiles
- **Single file**: clod.py is already large (~2776 lines) — may need to extract modules for new features
- **PyInstaller**: any new dependencies must be bundleable into the Windows EXE

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Confirm-before-switch (not full auto) | User wants visibility into routing decisions without friction | — Pending |
| Face swap service first priority | Self-contained, high-value, informs the routing architecture | — Pending |
| Natural language + slash commands | NL for convenience, slash commands as reliable fallback | — Pending |
| Chat model crafts SD prompts | llama3.1:8b is lightweight, good at conversational prompt building | — Pending |

---
*Last updated: 2026-03-10 after initialization*
