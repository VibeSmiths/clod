# Research Summary: Clod v2 -- Smart Routing & Media Generation

**Domain:** Local AI CLI with intent routing, face swap, VRAM-constrained model management
**Researched:** 2026-03-10
**Overall confidence:** MEDIUM-HIGH

## Executive Summary

Clod v2 adds three capabilities to the existing CLI: automatic intent detection and model routing, face swap/reference photo via ReActor, and VRAM-aware model management on a single 16 GB GPU. Research confirms all three are feasible with the current hardware and existing Docker infrastructure.

For intent classification, **semantic-router** (aurelio-labs, v0.1.12) is the right tool. It uses vector similarity over example utterances to classify user input in <10ms with no LLM call and no GPU overhead. This replaces the initial plan of regex+LLM tiered classification -- semantic-router handles the "fuzzy middle" (natural language that regex misses but LLM is overkill for) natively. It runs on CPU with all-MiniLM-L6-v2 embeddings (~44 MB), leaving GPU entirely free for inference models.

For face swap, **ReActor** wins on VRAM constraints. Its inswapper_128 model uses only ~260 MB VRAM on top of SD 1.5 (~4 GB), totaling ~6 GB for the full face swap pipeline. This leaves 10 GB free -- enough to reload any Ollama model afterward. The alternatives (InstantID at 10-20 GB, PuLID at 10+ GB) exceed the 16 GB budget when combined with any inference model. ReActor integrates as an extension in both AUTOMATIC1111 and ComfyUI, matching clod's existing dual Docker profile setup.

For VRAM management, Ollama's built-in `keep_alive` API provides everything needed. Setting `OLLAMA_MAX_LOADED_MODELS=1` and using `keep_alive: 0` to explicitly unload before SD/ComfyUI operations ensures no OOM crashes. The critical constraint is that 14b Ollama models (~9-10 GB) and SD (~4-6 GB) cannot coexist -- the router must always unload before switching between inference and generation.

## Key Findings

**Stack:** semantic-router (intent routing, <10ms, CPU-only) + ReActor (face swap, ~260 MB VRAM) + Ollama keep_alive API (VRAM management)

**Architecture:** Insert intent classifier between REPL input and infer() call. Semantic-router classifies, model router confirms with user and manages VRAM transitions, media handler dispatches to SD/ComfyUI APIs.

**Critical pitfall:** VRAM exhaustion from concurrent model loading is the highest risk. Ollama's default OLLAMA_MAX_LOADED_MODELS=3 will cause OOM or silent CPU fallback on 16 GB. Must set to 1 and always unload before switching contexts.

## Implications for Roadmap

Based on research, suggested phase structure:

1. **VRAM Management & Model Router** - Foundation phase
   - Addresses: OLLAMA_MAX_LOADED_MODELS=1, explicit unload API, VRAM verification
   - Avoids: OOM crashes, silent CPU fallback (Pitfall 2)
   - Rationale: Every other feature depends on reliable VRAM management

2. **Intent Classification** - Core routing phase
   - Addresses: semantic-router setup with 7 routes, startup embedding, per-input classification
   - Avoids: Over-engineering classifier (Pitfall 1), LLM-based classification latency
   - Rationale: Routing is the value proposition; must work before generation features

3. **Smart Model Routing + Confirm UX** - User-facing routing phase
   - Addresses: Intent-to-model mapping, confirm-before-switch, sticky intent within conversations
   - Avoids: State machine complexity (Pitfall 7), misclassification without recovery (Pitfall 5)
   - Rationale: Connects classifier to model management, delivers the "clod figures it out" experience

4. **Image/Video Generation Triggers** - Natural language generation phase
   - Addresses: NL triggers ("generate a picture of..."), chat-to-prompt pipeline, profile auto-switching
   - Avoids: Docker GPU lock on profile switch (Pitfall 3), A1111/ComfyUI API mismatch (Pitfall 8)
   - Rationale: Builds on routing; needs stable intent detection before wiring to SD/ComfyUI

5. **Face Swap Integration** - ReActor phase
   - Addresses: ReActor extension install, alwayson_scripts API, reference photo management
   - Avoids: ONNX version conflicts (Pitfall 4), first-use download blocking (Pitfall 9)
   - Rationale: Most complex feature; depends on VRAM management and media pipeline being solid

**Phase ordering rationale:**
- VRAM management is foundational -- without it, model switching causes OOM crashes
- Intent classification has no dependency on face swap, so it can be built first
- Face swap is the most complex and most isolated feature -- building it last allows the infrastructure (VRAM management, Docker orchestration) to be proven first
- Each phase delivers testable, independently valuable functionality

**Research flags for phases:**
- Phase 1 (VRAM): Standard Ollama API usage, unlikely to need deeper research
- Phase 2 (Intent): semantic-router is well-documented; may need research on optimal utterance sets
- Phase 3 (Routing): State machine design needs careful thought but pattern is well-known
- Phase 4 (Generation): ComfyUI API (WebSocket-based) likely needs phase-specific research
- Phase 5 (Face Swap): ReActor's alwayson_scripts API and ONNX runtime in container likely need phase-specific research

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack (intent routing) | HIGH | semantic-router is well-maintained, v0.1.12 verified, local execution documented |
| Stack (face swap) | MEDIUM-HIGH | ReActor is clear winner on VRAM; quality tradeoff vs IP-Adapter FaceID is acceptable |
| Stack (VRAM mgmt) | HIGH | Ollama API is well-documented; VRAM budget math verified against known model sizes |
| Features | HIGH | Table stakes and differentiators well-mapped; dependency graph is clear |
| Architecture | MEDIUM | Integration points with existing code are identified but ReActor API args need verification |
| Pitfalls | HIGH | VRAM exhaustion and ONNX conflicts are well-documented; mitigations are concrete |

## Gaps to Address

- **ReActor alwayson_scripts API arguments**: The exact arg format for ReActor in AUTOMATIC1111's API needs verification during the face swap phase. Tutorials show varying argument orders.
- **ComfyUI workflow API**: ComfyUI uses WebSocket-based workflow execution, not REST. The exact protocol for programmatic ComfyUI usage needs phase-specific research.
- **fastembed vs sentence-transformers in PyInstaller**: Need to verify that fastembed bundles cleanly with PyInstaller. ONNX Runtime may have dynamic library issues on Windows.
- **semantic-router route optimization**: The initial 5-10 utterances per route may need tuning after real-world testing. May need to add misclassification feedback loop.
- **Docker image for ReActor**: Whether to pre-bake ReActor into the SD Docker image or install at runtime needs a decision based on the current Dockerfile structure.

## Key Divergence from Prior Research

The existing ARCHITECTURE.md and PITFALLS.md recommend a **regex + LLM fallback** approach for intent classification. This stack research recommends **semantic-router** instead because:

1. Regex handles ~60% of inputs; semantic-router handles ~95% with the same effort
2. LLM fallback adds 500-2000ms per ambiguous input; semantic-router resolves in <10ms
3. semantic-router requires zero GPU/VRAM; LLM fallback requires a loaded model
4. Adding new intents = adding utterance examples, not writing more regex patterns

The PITFALLS.md warning about "over-engineering intent classification" (Pitfall 1) remains valid -- but semantic-router is the opposite of over-engineering. It is simpler than regex+LLM, not more complex. No training data, no ML pipeline, no model management -- just example utterances and vector math.
