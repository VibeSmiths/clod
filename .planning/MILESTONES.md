# Milestones

## v1.0 Smart Routing & Media Generation (Shipped: 2026-03-11)

**Phases completed:** 5 phases, 13 plans
**Timeline:** 2 days (2026-03-10 → 2026-03-11)
**Codebase:** 3,994 LOC Python (clod.py + intent.py), 498 unit tests, 91% coverage

**Key accomplishments:**
1. VRAM lifecycle management — safe model unloading, GPU memory verification, OLLAMA_MAX_LOADED_MODELS=1
2. Offline gating — auto-detect connectivity, block cloud calls when offline, Rich UI indicators
3. CPU-based intent classification — 7 intents via keyword regex + ONNX embeddings in <100ms
4. Smart model routing — auto-select Ollama model based on intent with "Switching to X for Y..." confirmation
5. Media generation pipeline — natural language image/video generation with docker profile orchestration
6. Comprehensive test suite — 498 unit tests, 91% coverage, CI enforcement gate at 90%

### Known Gaps
- **FACE-01 through FACE-05**: Face swap feature (Phase 5) deferred — split to separate project by user decision
- **Integration**: `image_edit` intent classified but not dispatched (silent no-op pending face swap)
- **Dependencies**: `numpy`, `onnxruntime`, `tokenizers` missing from requirements.txt (intent.py deps)

---

