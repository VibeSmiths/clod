# Domain Pitfalls

**Domain:** Local AI CLI with intent routing, VRAM-constrained model switching, face swap integration, and Docker profile orchestration
**Researched:** 2026-03-10

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or fundamental architecture problems.

### Pitfall 1: Over-Engineering Intent Classification

**What goes wrong:** Teams build a separate ML classifier (fine-tuned BERT, embedding-based router, multi-stage pipeline) for intent detection when the LLM itself can classify with a system prompt and structured output. This adds training data requirements, a model to maintain, and a cold-start problem -- all for 7 intent categories that a simple prompt can handle.

**Why it happens:** Developers default to "proper NLP" patterns from production chatbot architectures. For 50+ intents that makes sense. For chat/code/reason/vision/image-gen/video-gen/face-swap, it is massive over-engineering.

**Consequences:** Extra model to load (burns VRAM or CPU), latency added to every request, training data collection burden, drift between classifier categories and actual model capabilities, and a maintenance surface that grows with every new intent.

**Prevention:**
- Use the LLM itself for classification. A system prompt like "Classify this input as one of: chat, code, reason, vision, image_gen, video_gen, face_swap. Respond with JSON." works with even the 8b chat model.
- Add keyword shortcuts as a fast path before LLM classification: inputs starting with "generate a picture", "make a video", "swap my face" can be regex-matched without any LLM call.
- Reserve LLM-based classification for ambiguous inputs only. Most inputs are obviously chat or code.
- Keep the classifier as a pure function `classify_intent(text: str) -> Intent` that can be swapped later without touching routing logic.

**Detection:** If you find yourself collecting training data, building embedding indexes, or loading a second model just for routing -- stop. That is the warning sign.

**Phase mapping:** Intent detection phase. Get this right early because every downstream feature (model routing, docker switching, prompt crafting) depends on the intent signal.

---

### Pitfall 2: VRAM Exhaustion from Concurrent Model Loading

**What goes wrong:** Ollama's default `OLLAMA_MAX_LOADED_MODELS=3` tries to keep multiple models in VRAM simultaneously. On 16 GB, a 14b model (~10-12 GB) plus the face swap model (insightface/inswapper, ~1-2 GB ONNX) plus SD checkpoint (~4-6 GB) exceeds total VRAM. The system either OOMs, silently falls back to CPU inference (10-50x slower), or triggers constant model thrashing where every request evicts and reloads.

**Why it happens:** Ollama's eviction is automatic but not instant -- it takes 5-15 seconds to unload and reload a 14b model. Developers test with one model at a time and never hit the concurrent loading path. The SD/ComfyUI service also holds VRAM independently of Ollama, and these two systems have zero awareness of each other's VRAM usage.

**Consequences:**
- User switches from code (qwen2.5-coder:14b) to chat (llama3.1:8b) and waits 10-15 seconds for model swap instead of getting instant response.
- SD image generation fails with CUDA OOM because Ollama still has a 14b model loaded.
- Ollama silently spills to CPU after a VRAM-to-RAM overflow, and subsequent model loads all go to CPU even when VRAM frees up (known Ollama bug, [issue #11812](https://github.com/ollama/ollama/issues/11812)).

**Prevention:**
- Set `OLLAMA_MAX_LOADED_MODELS=1` in the Docker environment. On 16 GB with exclusive GPU profiles, only one LLM should be resident at a time.
- Set `OLLAMA_KEEP_ALIVE=5m` (the default) or shorter. Do not increase it -- fast eviction is better than OOM on this hardware.
- Before any SD/ComfyUI generation, explicitly unload the current Ollama model via `POST /api/generate {"model": "current", "keep_alive": 0}`. This frees VRAM for the image/video pipeline.
- Before switching back to LLM after generation, verify VRAM is actually free (check `nvidia-smi` or Ollama's model list endpoint).
- Reduce context window: `num_ctx: 2048` instead of default 4096 saves ~600-800 MB VRAM per model.
- Build a VRAM budget manager that tracks: Ollama model (size), SD/ComfyUI (loaded/unloaded), ReActor (loaded/unloaded). This is a simple state machine, not a complex allocator.

**Detection:** Watch for these symptoms: inference suddenly 10x slower (CPU fallback), CUDA OOM errors in SD logs, Ollama returning errors on model load, or `nvidia-smi` showing 15.9/16.0 GB used.

**Phase mapping:** Must be addressed in the model routing phase, before face swap or auto docker switching. The VRAM budget manager is foundational infrastructure.

---

### Pitfall 3: Docker Profile Switch Leaves GPU Locked

**What goes wrong:** When switching from `image` profile (AUTOMATIC1111 on port 7860) to `video` profile (ComfyUI on port 8188), the old container does not release its GPU reservation instantly. Running `docker compose --profile video up -d` while the image container is still shutting down causes either: (a) CUDA device already in use error, (b) the new container starts but cannot allocate GPU memory, or (c) both containers briefly run and OOM.

**Why it happens:** `docker compose --profile image down` is not instant. The SD container needs to unload models from VRAM and gracefully shut down, which can take 5-30 seconds depending on what is loaded. The `down` and `up` commands are separate shell invocations with no atomicity guarantee. The existing `sd_switch_mode` function in clod.py likely does sequential down/up without verifying GPU release between steps.

**Consequences:** Intermittent failures that are hard to reproduce. Works fine when SD has been idle (fast shutdown) but fails when switching right after a generation (models still in VRAM). Users see cryptic CUDA errors and have to manually restart Docker.

**Prevention:**
- Always run `down` first, then poll until the container is fully stopped AND GPU memory is freed before running `up`.
- Add a GPU release verification step: poll `nvidia-smi --query-gpu=memory.used --format=csv,noheader` until VRAM usage drops below a threshold (e.g., < 500 MB for Ollama's idle footprint).
- Set a timeout (30 seconds) on the GPU release poll. If it does not release, force-kill the container with `docker kill`.
- Use `docker compose --profile image down --timeout 15` to set a graceful shutdown deadline.
- Never run both profiles simultaneously -- the compose file already enforces this via separate profiles, but code must never issue both `up` commands.

**Detection:** If `nvidia-smi` shows high VRAM usage after `docker compose down` returns, the GPU is not yet released. If the new container logs show CUDA initialization errors, the old container's GPU handle is still held.

**Phase mapping:** Auto docker profile switching phase. This must be rock-solid before adding natural language triggers like "make a video of..." that automatically switch profiles.

---

### Pitfall 4: ReActor/InsightFace ONNX Runtime Version War

**What goes wrong:** ReActor depends on `insightface` which depends on `onnxruntime-gpu`. AUTOMATIC1111 may install a different version of onnxruntime. Other SD extensions (WD14 tagger, sd-cn-animation) actively reinstall conflicting onnxruntime versions on every WebUI startup. The result: ReActor works after manual install, breaks after next SD restart, works again after reinstall, breaks again. An endless cycle.

**Why it happens:** Python package management in SD extensions is a mess. Each extension has its own `install.py` that runs `pip install` on startup. There is no dependency resolution across extensions. The specific known conflict: onnxruntime-gpu >= 1.16.1 is required, but some extensions force onnxruntime == 1.16.0 (which has a known bug) or strip the `-gpu` suffix entirely, causing CPU-only face detection.

**Consequences:** Face swap silently falls back to CPU (slow, 10-30 seconds per face), or fails entirely with "CUDA provider not available" errors. Developers waste hours debugging version conflicts that reappear on every container restart.

**Prevention:**
- Run ReActor as a standalone Docker service, NOT as an SD extension. This isolates the Python environment completely. Use ReActor's API endpoint for face swap requests from clod.
- If running as SD extension: pin onnxruntime-gpu version in a post-install script that runs AFTER all extensions install. Add a health check that verifies CUDA provider is available.
- Do not install WD14 tagger or sd-cn-animation alongside ReActor unless version pinning is verified.
- Consider using ComfyUI-ReActor instead of sd-webui-reactor -- ComfyUI's extension system has fewer version conflicts.
- Test face swap in the CI/CD pipeline with a simple API call that verifies CUDA execution, not just import success.

**Detection:** Check ReActor logs for "Using CPU" or "CUDA provider not found". Run `python -c "import onnxruntime; print(onnxruntime.get_available_providers())"` inside the container -- if CUDAExecutionProvider is missing, the version conflict has struck again.

**Phase mapping:** Face swap service phase. Decide the deployment model (standalone container vs. SD extension) before writing any integration code.

---

## Moderate Pitfalls

### Pitfall 5: Intent Misclassification Without Graceful Recovery

**What goes wrong:** The intent classifier routes "write me a function that generates images" to image_gen instead of code. Or routes "what does this image show?" to image_gen instead of vision. The user gets an unexpected SD generation instead of a code response, wasting 30-60 seconds and GPU time.

**Prevention:**
- Always confirm before acting on high-cost intents (image_gen, video_gen, face_swap). The PROJECT.md already specifies "confirm-before-switch" -- enforce this for generation intents, not just model switches.
- Make confirmation skippable with a flag (`--yes`, or a session toggle) for power users who trust the classifier.
- Keep a misclassification escape hatch: if the user says "no" to a confirmation, ask what they actually meant and use that as a training signal (even if just logged for manual review).
- Weight the classifier toward chat/code as the default. Image/video/face_swap should require higher confidence or explicit trigger words.

**Detection:** Track confirmation rejection rate. If users reject > 20% of intent classifications, the classifier needs tuning.

**Phase mapping:** Intent detection phase, but the UX design must be settled before implementation.

---

### Pitfall 6: Chat-to-Prompt Pipeline Adds Unacceptable Latency

**What goes wrong:** The design calls for llama3.1:8b to craft SD/ComfyUI prompts from natural language. This adds a full LLM inference round-trip (2-8 seconds) before image generation even starts. Combined with model switch time (if switching from a different model) and SD generation time, the total wait becomes 30-60+ seconds from user input to first image.

**Prevention:**
- Keep the prompt-crafting model always loaded if possible. llama3.1:8b is ~5 GB -- with `OLLAMA_MAX_LOADED_MODELS=1` this means unloading the current model first. Consider whether the 8b model is worth loading just for prompt crafting.
- Alternative: Use the currently-loaded model for prompt crafting. qwen2.5-coder:14b can write SD prompts just fine. Avoid the model switch entirely.
- Show incremental progress: "Crafting prompt..." -> "Starting generation..." -> progress bar. Do not let the user stare at a blank screen.
- Cache prompt templates for common patterns. "A photo of X" does not need LLM prompt crafting.

**Detection:** Measure end-to-end latency from user input to first generation progress. If > 20 seconds before any visible generation progress, the pipeline has too many serial steps.

**Phase mapping:** Chat-to-prompt pipeline phase. Benchmark the full pipeline end-to-end before committing to the two-model approach.

---

### Pitfall 7: Model Routing Creates State Machine Complexity

**What goes wrong:** Intent -> model mapping seems simple (7 intents, 4-5 models) but state management explodes: What model is currently loaded? Is it being used? Is SD running? Which profile? Is a generation in progress? Can we interrupt? What if the user sends a chat message while an image is generating? Each state transition needs handling, and missed transitions cause silent failures or hung states.

**Prevention:**
- Model the system as an explicit state machine with defined states: IDLE, LLM_ACTIVE, SD_GENERATING, SWITCHING_MODEL, SWITCHING_PROFILE. Reject or queue requests that arrive in incompatible states.
- Store current state in session_state (which already exists) with a single `routing_state` key that is always one of the defined states. Never allow partial transitions.
- Make state transitions atomic: wrap the full switch sequence (unload old model -> verify VRAM -> load new model -> verify loaded) in a single function that either fully succeeds or fully rolls back.
- Log every state transition for debugging.

**Detection:** If you find yourself writing `if model == X and sd_running and profile == "image" and not generating:` nested conditionals, you have an implicit state machine that needs to be made explicit.

**Phase mapping:** Model routing phase. Define the state machine before implementing any switching logic.

---

### Pitfall 8: SD/ComfyUI API Differences Break Unified Generation Interface

**What goes wrong:** AUTOMATIC1111's API (`/sdapi/v1/txt2img`) and ComfyUI's API (WebSocket-based workflow execution) have completely different interfaces, authentication models, progress reporting mechanisms, and error formats. Building a "unified generation" abstraction that papers over these differences creates a leaky abstraction that breaks on edge cases.

**Prevention:**
- Do not build a unified abstraction. Build two separate, thin API clients: `A1111Client` and `ComfyUIClient`. Each handles its own protocol (REST vs WebSocket), progress reporting, and error handling.
- Share only the interface contract: `generate(prompt, params) -> GenerationResult`. The implementation details stay separate.
- ComfyUI uses workflow JSON, not simple prompt strings. The prompt-crafting pipeline needs to output different formats depending on the target backend.
- Test each client independently against its real API. Mock-based tests for API clients are nearly worthless -- the API quirks are the entire point.

**Detection:** If your generation abstraction has `if backend == "a1111": ... elif backend == "comfyui": ...` scattered throughout, the abstraction is not abstracting.

**Phase mapping:** Affects both image generation and video generation phases. Settle the API client design early.

---

## Minor Pitfalls

### Pitfall 9: Face Swap Model Downloads Block First Use

**What goes wrong:** ReActor requires downloading `inswapper_128.onnx` (~500 MB) and insightface analysis models (~300 MB) on first use. If these downloads happen lazily during the first face swap request, the user waits 2-10 minutes with no feedback, or the download times out and the request fails.

**Prevention:**
- Pre-download models during service setup / Docker image build, not on first request.
- If lazy download is unavoidable, show a progress bar and estimated time.
- Store models in a named Docker volume so they survive container recreation (the compose file already uses named volumes for ComfyUI models -- do the same for ReActor).

**Phase mapping:** Face swap service phase. Handle during Docker image configuration.

---

### Pitfall 10: Port Conflicts on Profile Switch Timing

**What goes wrong:** Both AUTOMATIC1111 and ComfyUI bind to different ports (7860 and 8188), so there is no direct port conflict between them. However, if a third service (like a ReActor standalone container) needs GPU access, or if health checks target the wrong port after a profile switch, stale service references cause failures.

**Prevention:**
- Update health check targets in `_check_service_health` after every profile switch. The health check must know which profile is active and only check the relevant service.
- Store the active profile in session_state and use it to gate which services are expected to be healthy.

**Phase mapping:** Auto docker switching phase.

---

### Pitfall 11: clod.py Monolith Makes New Features Untestable

**What goes wrong:** Adding intent classification, model routing state machine, VRAM budget manager, and generation clients to the existing 2776-line single file makes it unmaintainable. The CONCERNS.md already flags this. Every new feature makes it worse.

**Prevention:**
- Extract modules BEFORE adding new features, not after. Minimum extraction:
  - `clod/routing.py` -- intent classification + model selection + state machine
  - `clod/generation.py` -- A1111Client, ComfyUIClient, prompt crafting
  - `clod/vram.py` -- VRAM budget tracking, model loading/unloading
  - `clod/services.py` -- Docker profile management, health checks
- Keep `clod.py` as the thin REPL shell that delegates to these modules.
- This extraction is a prerequisite, not a "nice to have." Testing a state machine buried in a 3500-line file is impractical.

**Detection:** If any single file exceeds 500 lines of new feature code, it needs extraction.

**Phase mapping:** Should be Phase 0 / prerequisite before any feature work begins.

---

### Pitfall 12: Slash Command Explosion

**What goes wrong:** Adding `/faceswap`, `/generate image`, `/generate video`, `/route`, `/vram`, `/profile` on top of the existing 15+ slash commands creates a CLI with 20+ commands that users cannot remember. The natural language routing was supposed to reduce command burden, not increase it.

**Prevention:**
- Natural language should be the primary interface. Slash commands are fallbacks, not the main UX.
- Group related commands: `/generate` with subcommands (image, video, faceswap) instead of separate top-level commands.
- Do not add a slash command for anything the intent router handles. If `/generate image` works, the user should also be able to type "generate an image of a sunset" and get the same result.

**Phase mapping:** Slash command phase, but the grouping design should be decided during intent detection phase.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Module extraction | Breaking existing tests during refactor | Run full test suite after each extraction. Keep public API identical. |
| Intent detection | Over-engineering the classifier (Pitfall 1) | Start with regex fast-path + LLM fallback. No ML models. |
| Intent detection | Misclassification UX (Pitfall 5) | Confirm-before-switch for all generation intents. |
| Model routing | VRAM exhaustion (Pitfall 2) | Set OLLAMA_MAX_LOADED_MODELS=1, explicit unload before switch. |
| Model routing | State machine complexity (Pitfall 7) | Define states explicitly. No implicit state. |
| Chat-to-prompt | Latency stacking (Pitfall 6) | Use current model for prompt crafting. Avoid unnecessary model switch. |
| Face swap service | ONNX version wars (Pitfall 4) | Standalone Docker container, not SD extension. |
| Face swap service | First-use download block (Pitfall 9) | Pre-download models in Docker build. |
| Auto docker switch | GPU not released (Pitfall 3) | Poll nvidia-smi between down and up. |
| Auto docker switch | Health check staleness (Pitfall 10) | Track active profile in session_state. |
| Generation API | A1111/ComfyUI API mismatch (Pitfall 8) | Separate clients, shared interface only. |
| All phases | Monolith growth (Pitfall 11) | Extract modules first. |

## Sources

- [Ollama FAQ - Model Loading and VRAM](https://docs.ollama.com/faq) - HIGH confidence
- [Ollama Issue #11812 - CPU fallback after VRAM spill](https://github.com/ollama/ollama/issues/11812) - HIGH confidence
- [Ollama VRAM with Large Models](https://geekbacon.com/2025/05/03/understanding-vram-usage-in-ollama-with-large-models/) - MEDIUM confidence
- [Ollama Performance Tuning](https://collabnix.com/ollama-performance-tuning-gpu-optimization-techniques-for-production/) - MEDIUM confidence
- [ReActor SD-WebUI Extension (Codeberg)](https://codeberg.org/Gourieff/sd-webui-reactor) - HIGH confidence
- [ReActor ComfyUI Extension (GitHub)](https://github.com/Gourieff/ComfyUI-ReActor) - HIGH confidence
- [ONNX Runtime CUDA Provider Issue #15884](https://github.com/AUTOMATIC1111/stable-diffusion-webui/issues/15884) - HIGH confidence
- [Docker Compose Startup Order](https://docs.docker.com/compose/how-tos/startup-order/) - HIGH confidence
- [Docker Compose GPU Support](https://docs.docker.com/compose/how-tos/gpu-support/) - HIGH confidence
- [Intent Routing for AI Agents](https://medium.com/@roeyazroel/intent-routing-for-ai-agents-e075d64da6c9) - MEDIUM confidence
- [Intent Classification in Agentic LLM Apps](https://medium.com/@mr.murga/enhancing-intent-classification-and-error-handling-in-agentic-llm-applications-df2917d0a3cc) - MEDIUM confidence
- [Hybrid LLM + Intent Classification](https://medium.com/data-science-collective/intent-driven-natural-language-interface-a-hybrid-llm-intent-classification-approach-e1d96ad6f35d) - MEDIUM confidence

---

*Pitfalls audit: 2026-03-10*
