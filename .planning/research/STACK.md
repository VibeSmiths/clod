# Technology Stack

**Project:** Clod v2 -- Smart Routing & Media Generation
**Researched:** 2026-03-10

## Recommended Stack

### Intent Classification (Smart Routing)

| Technology | Version | Purpose | Why | VRAM |
|------------|---------|---------|-----|------|
| semantic-router | 0.1.12 | Intent classification & routing | Sub-10ms routing via vector similarity -- no LLM call needed. Define routes as utterance lists, embed at startup, classify via cosine similarity. Zero GPU overhead when using CPU encoder. Actively maintained by aurelio-labs. | ~44 MB (CPU preferred) |
| sentence-transformers (all-MiniLM-L6-v2) | 3.3+ | Local embedding encoder for semantic-router | 22M params, 384-dim embeddings, ~44 MB in FP16. Powers semantic-router's HuggingFaceEncoder for fully offline intent detection. Runs on CPU without meaningful latency impact. | ~44 MB or CPU-only |

**Confidence:** HIGH -- semantic-router v0.1.12 (Nov 2025) supports local encoders natively via `pip install "semantic-router[local]"`. The pattern maps directly to clod's 7-route classification need.

**How it works in clod:**

```python
from semantic_router import Route, SemanticRouter
from semantic_router.encoders import HuggingFaceEncoder

encoder = HuggingFaceEncoder(name="all-MiniLM-L6-v2")  # ~44 MB, CPU

routes = [
    Route(name="code", utterances=[
        "write a function that", "fix this bug", "refactor this class",
        "implement a parser", "debug this error",
    ]),
    Route(name="reason", utterances=[
        "explain why", "think through this", "analyze step by step",
        "what are the tradeoffs", "reason about",
    ]),
    Route(name="image_gen", utterances=[
        "generate a picture of", "create an image", "draw me",
        "make a photo of", "paint a scene",
    ]),
    Route(name="face_swap", utterances=[
        "put my face on", "swap my face", "face swap",
        "use my photo in", "make me look like",
    ]),
    # ... vision, video_gen, chat (default)
]

router = SemanticRouter(encoder=encoder, routes=routes)
result = router("write a python function to sort a list")
# result.name == "code", resolved in <10ms
```

**Why not alternatives:**

| Alternative | Why Not |
|-------------|---------|
| Fine-tuned DistilBERT | Requires labeled training data, training pipeline, model management. semantic-router achieves the same with 5-10 example utterances per route and zero training. |
| LLM-based classification (ask Ollama) | 500-2000ms latency per classification, consumes VRAM, unreliable with small models. 50-200x slower than semantic-router. |
| Regex/keyword matching | Brittle. "help me make myself look like an astronaut in space" would not match a `/faceswap` regex. semantic-router handles natural variation. |
| Pure regex + LLM fallback (tiered) | Better than LLM-only but still has failure modes on ambiguous inputs. semantic-router's vector approach handles the "fuzzy middle" that regex misses and LLM is overkill for. |

**Alternative for PyInstaller bundle size:** Use `fastembed` instead of sentence-transformers to avoid PyTorch dependency (~500 MB saved). semantic-router supports it via `FastEmbedEncoder`. Install: `pip install semantic-router fastembed`.

### Face Swap / Reference Photo

| Technology | Version | Purpose | Why | VRAM |
|------------|---------|---------|-----|------|
| ReActor (sd-webui-reactor) | latest | Face swap via AUTOMATIC1111 | Lightweight inswapper_128 model (~260 MB VRAM in FP16). Integrates as A1111 extension -- uses existing alwayson_scripts API. Works with SD 1.5 models. Total with SD ~6 GB VRAM. | ~260 MB on top of SD |
| ReActor (ComfyUI-ReActor) | latest | Face swap via ComfyUI | Same inswapper engine as ComfyUI node. Has "Unload ReActor Models" node for VRAM cleanup. Use when video profile is active. | ~260 MB on top of ComfyUI |
| CodeFormer / GFPGAN | built-in to A1111 | Face restoration post-swap | ReActor's 128x128 swap resolution requires face restoration for usable output. Both are built into AUTOMATIC1111. CodeFormer produces more natural results. | Minimal additional (~100 MB) |

**Confidence:** MEDIUM-HIGH -- ReActor is the clear winner on VRAM constraints. Quality is adequate for 512px output with face restoration. Architecture allows future upgrade to IP-Adapter FaceID if higher quality is needed.

**VRAM comparison of face swap options:**

| Method | Min VRAM | SD Model Req | Quality (identity) | Speed | 16 GB Feasible? |
|--------|----------|-------------|-------------------|-------|-----------------|
| ReActor (inswapper_128) | ~6 GB total with SD 1.5 | SD 1.5 (~4 GB) | 68% identity | ~5-10s | YES -- ~6 GB total, leaves 10 GB free |
| IP-Adapter FaceID | ~8 GB with SD 1.5 | SD 1.5 + ControlNet + LoRA | 79% identity | ~10-15s | YES but tight -- no room for Ollama |
| InstantID | ~10-20 GB | SDXL only (~6 GB) | 84% identity | ~15-20s | NO -- exceeds budget with SDXL |
| PuLID | ~10+ GB | Flux model | 91% identity | ~35s | NO -- Flux alone fills 16 GB |

**Why ReActor wins for clod:**
1. Fits within VRAM budget with room for model swaps (~6 GB for SD+ReActor, 10 GB free)
2. Works with both AUTOMATIC1111 and ComfyUI (matching clod's dual Docker profiles)
3. Can be driven via AUTOMATIC1111's REST API (`/sdapi/v1/txt2img` with `alwayson_scripts`)
4. inswapper_128 model is small (~554 MB disk, ~260 MB VRAM in FP16)
5. Face restoration (CodeFormer/GFPGAN) is already built into AUTOMATIC1111

**Upgrade path:** If users need higher quality, IP-Adapter FaceID can work with SD 1.5 at ~8 GB total. This requires unloading Ollama first but is feasible. Design the face swap abstraction to support swapping backends later.

### VRAM-Aware Model Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Ollama keep_alive API | built-in | Explicit model unloading | `POST /api/generate {"model":"X","keep_alive":0}` immediately frees VRAM. No new dependency. |
| Ollama /api/ps endpoint | built-in | Query loaded models | Returns model names and VRAM sizes. Use to verify state before transitions. |
| OLLAMA_MAX_LOADED_MODELS=1 | env var | Prevent concurrent loads | Default is 3 -- dangerous on 16 GB. Force single model to prevent OOM. |
| OLLAMA_KEEP_ALIVE=5m | env var | Auto-unload timer | 5 minutes (default). Do not increase. Shorter is safer on constrained VRAM. |
| nvidia-smi (subprocess) | system | VRAM verification | `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits` for precise free VRAM check before loading. Already available via psutil/subprocess. |

**Confidence:** HIGH -- Ollama's keep_alive API and /api/ps endpoint are well-documented. The VRAM budget math is based on known model sizes from Ollama's model library.

**VRAM Budget (16 GB RTX 4070 Ti SUPER):**

| Scenario | Components | VRAM Used | Free | Notes |
|----------|-----------|-----------|------|-------|
| Code work | qwen2.5-coder:14b | ~10 GB | ~6 GB | Normal operation |
| Reasoning | deepseek-r1:14b | ~9 GB | ~7 GB | Normal operation |
| Quick chat | llama3.1:8b | ~5 GB | ~11 GB | Lightweight |
| Vision | qwen2.5vl:7b | ~5 GB | ~11 GB | Lightweight |
| Image gen | SD 1.5 + ReActor | ~6 GB | ~10 GB | Must unload Ollama first |
| Face swap | SD 1.5 + ReActor + CodeFormer | ~6.5 GB | ~9.5 GB | Must unload Ollama first |
| Intent routing | all-MiniLM-L6-v2 (CPU) | ~0 GB GPU | N/A | Runs on CPU, no VRAM impact |

**Critical constraint:** Ollama 14b models (~9-10 GB) and SD (~4-6 GB) cannot coexist. The router must:
1. Unload Ollama model via `keep_alive: 0`
2. Verify VRAM freed via nvidia-smi or /api/ps
3. Start SD generation
4. After generation, Ollama lazy-loads on next chat request (~2-5s cold start)

### Supporting Libraries (New Dependencies)

| Library | Version | Purpose | Bundle Impact | PyInstaller |
|---------|---------|---------|---------------|-------------|
| semantic-router | 0.1.12 | Intent routing (core) | ~5 MB (pure Python) | Yes |
| fastembed | 0.4+ | ONNX-based embeddings (lighter than PyTorch) | ~50 MB (onnxruntime) | Yes |
| sentence-transformers | 3.3+ | Alternative encoder (if PyTorch already bundled) | ~500 MB (PyTorch) | Yes but heavy |

**Recommendation:** Use `fastembed` for the EXE build to avoid adding PyTorch (~500 MB). Use `sentence-transformers` for development/pip-install path where PyTorch overhead is acceptable.

```bash
# For EXE builds (lightweight):
pip install semantic-router fastembed

# For development (full-featured):
pip install "semantic-router[local]"
```

**Container-side dependencies (not bundled in clod):**

| Library | Where | Purpose |
|---------|-------|---------|
| insightface 0.7+ | A1111/ComfyUI container | Face detection for ReActor |
| onnxruntime-gpu 1.17+ | A1111/ComfyUI container | ONNX model inference (CUDA) |
| inswapper_128.onnx | A1111/ComfyUI container | Face swap model (~554 MB) |

## Configuration Changes

```bash
# .env additions for smart routing
OLLAMA_MAX_LOADED_MODELS=1          # Force single model (prevent OOM)
OLLAMA_KEEP_ALIVE=5m                # Auto-unload after 5 min idle

# Feature flags
INTENT_ROUTER_ENABLED=true          # Enable smart routing
INTENT_CONFIDENCE_THRESHOLD=0.7     # Below this, use current model (no switch)
REACTOR_ENABLED=true                # Enable face swap capability

# ReActor model paths (container-side)
REACTOR_MODEL=inswapper_128.onnx
REACTOR_FACE_RESTORER=CodeFormer
```

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Intent routing | semantic-router + fastembed | LLM classification prompt | 50-200x slower, wastes GPU, unreliable with small models |
| Intent routing | semantic-router | Regex + LLM fallback (tiered) | Regex misses natural language variations; semantic-router handles the fuzzy middle natively |
| Intent routing | semantic-router | Fine-tuned DistilBERT | Requires training data pipeline; semantic-router works with example utterances only |
| Face swap | ReActor | IP-Adapter FaceID | Higher VRAM (~8 GB), requires ControlNet + LoRA, marginal quality gain at 512px |
| Face swap | ReActor | InstantID | 10-20 GB VRAM, SDXL-only, exceeds 16 GB budget |
| Face swap | ReActor | PuLID | Best quality (91%) but requires Flux, 10+ GB VRAM, 35s/image |
| Face swap | ReActor | Roop | Deprecated predecessor; ReActor is the maintained fork |
| Embeddings (EXE) | fastembed | sentence-transformers | PyTorch adds ~500 MB to EXE bundle |
| Embeddings (dev) | sentence-transformers | OpenAI API | Requires internet, defeats local-first goal |
| VRAM mgmt | Ollama keep_alive API | External VRAM allocator | Unnecessary complexity; Ollama handles natively |

## Installation

```bash
# Smart routing (choose one):
pip install semantic-router fastembed          # Lightweight (for EXE builds)
pip install "semantic-router[local]"           # Full (for development)

# Face swap (inside A1111 Docker container):
# Option A: Install as extension via WebUI
#   Extensions > Install from URL > https://github.com/Gourieff/sd-webui-reactor
# Option B: Pre-install in Dockerfile
#   RUN cd /app/extensions && git clone https://github.com/Gourieff/sd-webui-reactor

# Face swap (inside ComfyUI Docker container):
#   Install via ComfyUI Manager or:
#   RUN cd /app/custom_nodes && git clone https://github.com/Gourieff/ComfyUI-ReActor

# VRAM management (no new deps):
# Add to .env:
#   OLLAMA_MAX_LOADED_MODELS=1
#   OLLAMA_KEEP_ALIVE=5m

# Update requirements.txt:
# semantic-router>=0.1.12
# fastembed>=0.4.0
```

## Sources

- [semantic-router GitHub](https://github.com/aurelio-labs/semantic-router) -- v0.1.12 (Nov 2025), HIGH confidence
- [semantic-router local execution docs](https://github.com/aurelio-labs/semantic-router/blob/main/docs/05-local-execution.ipynb) -- HIGH confidence
- [all-MiniLM-L6-v2 memory requirements](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/discussions/39) -- ~44 MB FP16, HIGH confidence
- [Ollama FAQ -- model unloading](https://docs.ollama.com/faq) -- keep_alive=0, OLLAMA_MAX_LOADED_MODELS, HIGH confidence
- [Ollama VRAM management](https://deepwiki.com/ollama/ollama/5.4-memory-management-and-gpu-allocation) -- MEDIUM confidence
- [Ollama model unloading practical guide](https://pauleasterbrooks.com/articles/technology/clearing-ollama-memory) -- MEDIUM confidence
- [ReActor A1111 extension](https://github.com/Gourieff/sd-webui-reactor) -- face swap via inswapper_128, HIGH confidence
- [ReActor ComfyUI extension](https://github.com/Gourieff/ComfyUI-ReActor) -- ComfyUI node version, HIGH confidence
- [InstantID vs PuLID vs FaceID comparison 2025](https://apatero.com/blog/instantid-vs-pulid-vs-faceid-ultimate-face-swap-comparison-2025) -- VRAM/quality benchmarks, MEDIUM confidence
- [IP-Adapter FaceID on HuggingFace](https://huggingface.co/h94/IP-Adapter-FaceID) -- MEDIUM confidence
- [inswapper model analysis](https://www.1337sheets.com/p/comparing-face-swap-models-blendswap-ghost-inswapper-simswap-uniface) -- ~130M params, ~260 MB FP16, MEDIUM confidence
- [Ollama GPU optimization](https://collabnix.com/ollama-performance-tuning-gpu-optimization-techniques-for-production/) -- MEDIUM confidence
