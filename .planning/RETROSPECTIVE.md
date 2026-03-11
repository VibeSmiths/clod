# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Smart Routing & Media Generation

**Shipped:** 2026-03-11
**Phases:** 5 | **Plans:** 13

### What Was Built
- VRAM lifecycle management with safe model unloading and GPU memory verification
- CPU-based intent classification (7 intents, <100ms, keyword regex + ONNX embeddings)
- Smart model routing — auto-select Ollama model with confirmation UX
- Natural language image/video generation with docker profile orchestration
- 498 unit tests at 91% coverage with CI enforcement gate

### What Worked
- Phase dependency ordering: VRAM first (everything depends on it) → intent → routing → generation was the right sequence
- Verification loop after each phase caught real gaps (Phase 1 VRAM functions were dead code until re-verification)
- Single-file architecture (clod.py) kept integration simple — functions call each other directly
- ONNX UINT8/AVX2 model choice avoided GPU contention entirely for intent classification
- try/finally pattern for model restore prevented orphaned GPU state across all generation paths

### What Was Inefficient
- SUMMARY frontmatter `requirements_completed` never populated across all 13 plans — 3-source cross-reference at audit time fell back to 2 sources
- Phase 5 (Face Swap) was in the roadmap from the start but never planned — should have been flagged earlier or scoped out during roadmap creation
- ROADMAP.md checkboxes went stale for Phase 6 (showed 2/3 when 3/3 were complete)
- `image_edit` intent was classified in Phase 2 but never wired to a handler through Phase 4 — silent no-op discovered only at audit

### Patterns Established
- VRAM handoff sequence: unload → verify → start → poll (reused across /model, /sd, generation)
- Confirm-then-auto-proceed UX: cyan message + no blocking prompt (routing, profile switches)
- Generation pipeline: craft prompt via chat model → unload → generate → restore model
- Docker profile orchestration: detect → warn → confirm → switch → verify VRAM
- FakeConsole wrapper for Rich Progress/Live compatibility in unit tests

### Key Lessons
1. Wire functions into live handlers immediately — dead code passes verification until someone checks call sites
2. Intent intents mapped to None need explicit "not yet supported" messages, not silent fallthrough
3. Missing Python dependencies are masked by try/except import guards — CI should test imports explicitly
4. SUMMARY frontmatter should be populated by the executor, not left for audit to discover empty

### Cost Observations
- Model mix: predominantly sonnet agents with opus orchestration
- 13 plans executed in ~2 hours total wall clock
- Verification re-runs caught real issues (Phase 1 needed a third plan for wiring)

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 5 | 13 | First milestone — established verification + audit pattern |

### Cumulative Quality

| Milestone | Tests | Coverage | Known Gaps |
|-----------|-------|----------|------------|
| v1.0 | 498 | 91% | 3 (deps, image_edit, summary frontmatter) |

### Top Lessons (Verified Across Milestones)

1. Wire code to call sites in the same plan that creates it — defer = dead code
2. Every classified intent needs a handler or explicit "unsupported" message
