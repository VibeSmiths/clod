# Phase 2: Intent Classification - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Classify every user input into one of 6+ intents (chat, code, reason, vision, image-gen, image-edit, video-gen) before any routing decision. Classification must be CPU-only, under 100ms, and bypassable via `/model`. This phase builds the classifier only — Phase 3 acts on it for model routing.

</domain>

<decisions>
## Implementation Decisions

### Classification Approach
- Hybrid architecture: keyword/regex rules catch obvious cases first, lightweight embedding model handles ambiguous input
- Keyword layer aggressiveness: Claude's discretion — balance between trigger phrases and broader keyword scanning based on testing
- Embedding model: ~100MB class (e.g. all-mpnet-base-v2), bundled directly in PyInstaller EXE — no first-run download
- Must meet <100ms CPU-only constraint per INTENT-02

### Intent Boundaries
- Code vs chat is context-dependent: "write a function" = code, "tell me a joke" = chat. Use surrounding keywords to disambiguate
- Reasoning uses hybrid signal: analytical framing ("explain why", "analyze") + code context = reason. Just code terms without analytical framing = code
- Image generation has two sub-intents: image-gen (create new) vs image-edit (modify existing). Different workflows downstream
- Vision intent triggering: Claude's discretion (image attachments, visual keywords, or both)
- Video-gen: natural language triggers like "make a video of..."

### Low-Confidence Handling
- High confidence threshold: >0.8 to auto-classify. Below 0.8 = ask the user
- User prompt on low confidence: Claude's discretion on format (inline one-liner vs Rich panel), should fit existing console patterns
- Session memory for rejected suggestions: Claude's discretion on whether to suppress repeated suggestions

### Classification UX
- Show detected intent only when it would cause a model switch — stay silent when staying on current model
- Debug tooling: `/intent` slash command for one-shot classification check + verbose toggle for extended debugging
- After `/model` manual switch: classification is disabled until explicitly re-enabled (e.g., `/intent auto` or new session)
- REPL prompt style: Claude's discretion on whether to show intent alongside model name

### Claude's Discretion
- Keyword layer aggressiveness and exact patterns
- Vision intent triggering logic
- Low-confidence prompt format (inline vs Rich panel)
- Whether to remember rejected intent suggestions per session
- REPL prompt format (show intent or not)
- Embedding model warm-up strategy (eager vs lazy)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pick_adapter()` (clod.py:1703): Currently routes by model prefix — intent classification feeds into this or runs before it
- `infer()` (clod.py:2235): Entry point for inference — classification hooks in before adapter selection
- `handle_slash()` (clod.py:2324): Slash command handler — `/intent` and `/intent auto` commands go here
- `_enforce_offline()`: Offline gating pattern — similar gating approach for intent override mode
- Session state dict: Already carries `model`, `offline`, `features` — extend with `intent`, `intent_enabled` flags

### Established Patterns
- Slash commands handled in `handle_slash()` with string matching on `user_input`
- Rich console for panels, dim text, progress bars — use for intent display and debug output
- Session state dict is the central state carrier through the REPL loop
- Private functions prefixed with `_` for internal helpers
- Section comments: `# ── Section Name ─────────────────────────────`

### Integration Points
- `run_repl()` (clod.py:2844): Main REPL loop at line 2940 — classification runs on `user_input` before `infer()` call
- `pick_adapter()` (clod.py:1703): Classification result informs model selection (Phase 3 wires this)
- `handle_slash()`: Add `/intent` command for debug and `/intent auto` for re-enabling
- `clod.spec`: PyInstaller spec needs update to bundle embedding model files

</code_context>

<specifics>
## Specific Ideas

- From Phase 1 context: "I want it to warn if it needs to switch modes or models" — classification is the detection layer for this
- User wants high confidence bar (>0.8) before auto-routing — prefer asking over wrong guesses
- `/model` should feel like a hard override that stops classification from nagging until you opt back in
- Two debug modes: quick `/intent` check and persistent verbose toggle — covers both casual and troubleshooting use

</specifics>

<deferred>
## Deferred Ideas

- Image-edit sub-intent may need its own downstream handling beyond just classification — Phase 4 or later
- Session intent memory / learning from user corrections — ROUTE-05 is explicitly v2
- Confidence scores in confirm UX — ROUTE-04 is explicitly v2

</deferred>

---

*Phase: 02-intent-classification*
*Context gathered: 2026-03-10*
