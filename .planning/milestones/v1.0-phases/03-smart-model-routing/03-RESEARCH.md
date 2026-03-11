# Phase 3: Smart Model Routing - Research

**Researched:** 2026-03-10
**Domain:** Ollama model switching, Rich UI feedback, REPL routing logic
**Confidence:** HIGH

## Summary

Phase 3 transforms the passive intent classification from Phase 2 into active model routing. The classifier already produces `(intent, confidence)` tuples stored in `session_state["last_intent"]` and `session_state["last_confidence"]`. Phase 3 adds: (1) an intent-to-model mapping dict, (2) a routing decision function that compares the mapped model against the currently loaded model, (3) a brief auto-proceeding confirmation message, and (4) Rich spinner/progress bar for the swap/pull operations.

All building blocks exist in the codebase. `_ensure_model_ready()` already handles unload-verify-pull-warmup with VRAM safety. `ollama_pull()` already streams NDJSON progress. `warmup_ollama_model()` already uses `console.status()` spinner. The work is primarily wiring -- connecting the classifier output to the model switching pipeline with appropriate UX.

**Primary recommendation:** Create an `INTENT_MODEL_MAP` dict in clod.py mapping intent strings to Ollama model names, a `_route_to_model()` function that checks if a switch is needed and shows confirmation, and upgrade `ollama_pull()` to use `rich.progress.Progress` for proper progress bars.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ROUTE-01 | Auto-select Ollama model based on detected intent (chat->llama3.1:8b, code->qwen2.5-coder:14b, reason->deepseek-r1:14b, vision->qwen2.5vl:7b) | INTENT_MODEL_MAP dict + routing function using existing `_ensure_model_ready()` |
| ROUTE-02 | Show confirmation message before switching ("Switching to X for Y...") that auto-proceeds unless cancelled | Timed confirmation with `console.input()` or auto-proceed after brief display |
| ROUTE-03 | Rich spinner for quick swaps, progress bar for first-time pulls | `console.status()` spinner already used by `warmup_ollama_model()`; upgrade `ollama_pull()` to `rich.progress.Progress` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| rich | (already installed) | Spinner via `console.status()`, Progress bar via `rich.progress.Progress` | Already used throughout clod.py |
| requests | (already installed) | Ollama API calls for model management | Already used for all Ollama interactions |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich.progress | (part of rich) | Progress bar with download tracking | During `ollama_pull()` for first-time model downloads |

No new dependencies needed. Everything is already in the project.

## Architecture Patterns

### Recommended Changes Structure
```
clod.py
  +  INTENT_MODEL_MAP dict (near existing PIPELINE_CONFIGS, ~line 85)
  +  _route_to_model() function (near existing _ensure_model_ready, ~line 662)
  ~  REPL loop: replace passive comment with _route_to_model() call (~line 3020)
  ~  ollama_pull(): upgrade ASCII progress to rich.progress.Progress (~line 434)
```

### Pattern 1: Intent-to-Model Mapping
**What:** A simple dict mapping intent strings to Ollama model names
**When to use:** Every time the classifier returns a result and routing is enabled
**Example:**
```python
# Source: project requirements + CLAUDE.md model assignments
INTENT_MODEL_MAP: dict[str, str] = {
    "chat":       "llama3.1:8b",
    "code":       "qwen2.5-coder:14b",
    "reason":     "deepseek-r1:14b",
    "vision":     "qwen2.5vl:7b",
    "image_gen":  None,  # Phase 4 -- not routed to Ollama model
    "image_edit": None,  # Phase 4
    "video_gen":  None,  # Phase 4
}
```

### Pattern 2: Routing Decision Function
**What:** Function that takes intent+confidence from session_state, looks up target model, and triggers switch if needed
**When to use:** Called in REPL loop after classification, before `infer()`
**Key logic:**
```python
def _route_to_model(intent, confidence, session_state, console_obj):
    """Route to appropriate model based on classified intent.

    Returns True if routing proceeded (switch happened or no switch needed).
    Returns False if user cancelled.
    """
    if confidence < 0.8:
        return True  # Low confidence -- stay on current model

    target = INTENT_MODEL_MAP.get(intent)
    if target is None:
        return True  # Non-model intents (image_gen, etc.) -- Phase 4

    current = session_state["model"]
    if current == target:
        return True  # Already on the right model

    # Show confirmation and auto-proceed
    console_obj.print(
        f"[cyan]Switching to [bold]{target}[/bold] for {intent}...[/cyan]"
    )
    # Brief pause for user to see/cancel (see ROUTE-02 pattern below)

    # Use existing _ensure_model_ready with confirm=False (auto-proceed)
    return _ensure_model_ready(target, cfg, console_obj, session_state, confirm=False)
```

### Pattern 3: Auto-Proceeding Confirmation (ROUTE-02)
**What:** Display "Switching to X for Y..." message that auto-proceeds unless user presses Ctrl+C
**When to use:** Before every model switch triggered by routing
**Design choices:**
- Option A: Print message + proceed immediately (simplest, message is informational only)
- Option B: Print message + `time.sleep(1.5)` with KeyboardInterrupt catch for cancel
- Option C: Prompt with timeout using prompt_toolkit

**Recommendation:** Option A (print and proceed). The message satisfies ROUTE-02's "auto-proceeds unless cancelled" -- the user can Ctrl+C the entire operation. A sleep delay would add latency to every switch and frustrate users. The existing `_ensure_model_ready()` already handles the heavy lifting.

### Pattern 4: Rich Progress for Model Pulls (ROUTE-03)
**What:** Replace ASCII progress bar in `ollama_pull()` with `rich.progress.Progress`
**When to use:** During first-time model downloads
**Example:**
```python
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn

def ollama_pull(model: str, ollama_url: str) -> None:
    console.print(f"[dim]Pulling [bold]{model}[/bold] from Ollama registry...[/dim]")
    # ... request setup ...

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Pulling {model}", total=None)
        for raw in resp.iter_lines():
            event = json.loads(raw)
            total = event.get("total", 0)
            completed = event.get("completed", 0)
            if total:
                progress.update(task, total=total, completed=completed)
            else:
                progress.update(task, description=event.get("status", ""))
```

### Pattern 5: Spinner for Quick Swaps
**What:** `console.status()` spinner during model warmup (already exists in `warmup_ollama_model()`)
**Current implementation:** Already uses `console.status(f"Loading {model} into memory...", spinner="dots")`
**No change needed** -- `warmup_ollama_model()` already shows a spinner. The spinner is visible during quick swaps where the model is already downloaded but needs to be loaded into VRAM.

### Anti-Patterns to Avoid
- **Duplicating VRAM logic:** Do NOT re-implement unload/verify/pull/warmup. Use `_ensure_model_ready()` which already does all of this safely.
- **Blocking confirmation prompts:** Do NOT use `console.input()` for routing confirmation. This blocks the REPL and defeats the "auto-proceed" requirement. Print-and-proceed is correct.
- **Routing non-model intents:** `image_gen`, `image_edit`, `video_gen` intents should NOT trigger model routing in Phase 3. These are handled in Phase 4 (Media Generation Pipeline). Map them to `None` and skip.
- **Routing when intent_enabled is False:** The `/model` override from Phase 2 sets `intent_enabled = False`. Routing MUST respect this -- if `intent_enabled` is False, no auto-routing.
- **Routing cloud models:** If current model has a CLOUD_MODEL_PREFIX, do NOT auto-route to a local model. Cloud models were explicitly selected.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Model unload/load lifecycle | Custom unload + pull + warmup | `_ensure_model_ready()` | Already handles VRAM verification, retry, polling |
| Progress bars | ASCII art with `\r` | `rich.progress.Progress` | Handles terminal width, multiple tasks, speed calc |
| Spinner during load | Custom animation | `console.status()` | Already used by `warmup_ollama_model()` |
| Model availability check | Custom HTTP check | `ollama_model_available()` + `ensure_ollama_model()` | Already handles pull-if-needed |

**Key insight:** Phase 1 built the entire model lifecycle infrastructure. Phase 3 is wiring, not building.

## Common Pitfalls

### Pitfall 1: Re-routing on Every Message
**What goes wrong:** If user asks 3 code questions in a row, the system tries to "switch" to qwen2.5-coder:14b each time, showing confirmation messages for a model that's already loaded.
**Why it happens:** Not checking if current model matches target before routing.
**How to avoid:** Compare `session_state["model"]` to `INTENT_MODEL_MAP[intent]` before any switch logic. Skip if already on target.
**Warning signs:** Repeated "Switching to..." messages when model hasn't changed.

### Pitfall 2: Routing During Cloud Model Sessions
**What goes wrong:** User manually selected `claude-sonnet` via `/model`, then types a code question. Router tries to switch to `qwen2.5-coder:14b`.
**Why it happens:** Not checking if intent_enabled is False (which /model sets).
**How to avoid:** `intent_enabled` is already set to False by `/model` handler. The REPL loop already gates classification on `intent_enabled`. Routing should be inside the same gate.
**Warning signs:** Unexpected model switches after explicit `/model` usage.

### Pitfall 3: Low-Confidence Routing Loops
**What goes wrong:** Ambiguous input classified as "reason" with 0.72 confidence. System switches to deepseek-r1:14b. User's next message is still ambiguous but classified as "code" (0.71). System switches again.
**Why it happens:** Routing on low-confidence classifications.
**How to avoid:** Only route when confidence >= threshold (0.8). Below threshold, keep current model. The Phase 2 REPL loop already prints a "Low confidence" message for sub-0.8 results.
**Warning signs:** Frequent back-and-forth model switches.

### Pitfall 4: Forgetting to Re-enable Routing After /intent auto
**What goes wrong:** User uses `/model X` (disables intent_enabled), then uses `/intent auto` (re-enables). But the routing code checks a different flag or doesn't exist yet.
**Why it happens:** Phase 2 only did passive classification. Phase 3 adds routing that must respect the same `intent_enabled` flag.
**How to avoid:** Routing logic lives inside the same `if HAS_INTENT and session_state["intent_enabled"]:` block that already exists at line 3009.

### Pitfall 5: _ensure_model_ready confirm=True Blocking Auto-Route
**What goes wrong:** `_ensure_model_ready()` with default `confirm=True` shows "This needs X. Switch? [y/N]" prompt, defeating auto-proceed.
**Why it happens:** Using the function with wrong parameter.
**How to avoid:** Call `_ensure_model_ready(target, cfg, console, session_state, confirm=False)` for auto-routing. The ROUTE-02 confirmation message is a separate print statement, not a blocking prompt.

## Code Examples

### REPL Loop Integration Point (line ~3009)
```python
# Current code (Phase 2 passive):
if HAS_INTENT and session_state["intent_enabled"]:
    intent, confidence = classify_intent(user_input)
    session_state["last_intent"] = intent
    session_state["last_confidence"] = confidence
    if session_state.get("intent_verbose"):
        console.print(f"[dim]Intent: {intent} ({confidence:.2f})[/dim]")
    if confidence < 0.8:
        console.print(f"[dim]Low confidence intent: ...")
    # Note: actual model switching happens in Phase 3

# Phase 3 addition (replace the comment):
    # --- Smart Model Routing (Phase 3) ---
    target_model = INTENT_MODEL_MAP.get(intent)
    if target_model and confidence >= 0.8 and target_model != session_state["model"]:
        console.print(
            f"[cyan]Switching to [bold]{target_model}[/bold] for {intent}...[/cyan]"
        )
        ok = _ensure_model_ready(
            target_model, session_state["cfg"], console, session_state, confirm=False
        )
        if not ok:
            console.print("[dim]Model switch failed, continuing with current model.[/dim]")
```

### Rich Progress Bar for ollama_pull()
```python
from rich.progress import Progress, BarColumn, TextColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn

def ollama_pull(model: str, ollama_url: str) -> None:
    console.print(f"[dim]Pulling [bold]{model}[/bold] from Ollama registry...[/dim]")
    try:
        resp = requests.post(
            f"{ollama_url}/api/pull",
            json={"name": model, "stream": True},
            stream=True,
            timeout=3600,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        console.print(f"[red]Cannot connect to Ollama at {ollama_url}[/red]")
        return
    except requests.HTTPError as e:
        console.print(f"[red]Ollama pull error: {e}[/red]")
        return

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Pulling {model}", total=None)
        for raw in resp.iter_lines():
            if not raw:
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            status = event.get("status", "")
            total = event.get("total", 0)
            completed = event.get("completed", 0)
            if total:
                progress.update(task, total=total, completed=completed,
                                description=status)
            else:
                progress.update(task, description=status)

    console.print(f"[green]done[/green] [bold]{model}[/bold] ready")
```

### Test Pattern for Routing
```python
# Test: routing switches model when intent differs from current
def test_route_switches_model_on_code_intent(monkeypatch, mock_session_state):
    mock_session_state["model"] = "llama3.1:8b"  # Currently on chat model
    mock_session_state["intent_enabled"] = True

    # Mock classify_intent to return code intent
    monkeypatch.setattr(clod, "classify_intent", lambda text: ("code", 0.95))
    # Mock _ensure_model_ready to succeed
    monkeypatch.setattr(clod, "_ensure_model_ready", lambda *a, **kw: True)

    # Simulate REPL classification + routing
    # After routing, model should be qwen2.5-coder:14b
    assert mock_session_state["model"] == "qwen2.5-coder:14b"  # set by _ensure_model_ready

# Test: no switch when confidence is low
def test_route_no_switch_low_confidence(monkeypatch, mock_session_state):
    mock_session_state["model"] = "llama3.1:8b"
    monkeypatch.setattr(clod, "classify_intent", lambda text: ("reason", 0.65))
    # Model should remain unchanged
    assert mock_session_state["model"] == "llama3.1:8b"

# Test: no switch when already on target model
def test_route_no_switch_when_already_on_target(monkeypatch, mock_session_state):
    mock_session_state["model"] = "qwen2.5-coder:14b"
    monkeypatch.setattr(clod, "classify_intent", lambda text: ("code", 0.95))
    # _ensure_model_ready should NOT be called
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual `/model` switching | Auto-routing from intent | Phase 3 (now) | Core value proposition |
| ASCII progress `#---` | Rich Progress bars | Phase 3 (now) | Better UX for model pulls |
| Passive classification (Phase 2) | Active routing (Phase 3) | Phase 3 (now) | Classification becomes actionable |

## Open Questions

1. **What happens for image_gen/image_edit/video_gen intents?**
   - What we know: These intents need special handling (docker services, not just Ollama models)
   - What's unclear: Nothing -- they are explicitly Phase 4 scope
   - Recommendation: Map to `None` in INTENT_MODEL_MAP, skip routing, leave for Phase 4

2. **Should routing have a "sticky" mode?**
   - What we know: ROUTE-05 (v2) mentions "session intent memory -- consecutive same-intent messages stay on current model without re-confirming"
   - What's unclear: Whether any stickiness is needed in v1
   - Recommendation: No stickiness in Phase 3. The "already on target model" check naturally handles consecutive same-intent messages. v2 ROUTE-05 can add persistence logic later.

3. **Should the confirmation message include confidence?**
   - What we know: ROUTE-04 (v2) says "confidence scores displayed in confirm UX"
   - What's unclear: Whether to show confidence in v1
   - Recommendation: No. v1 just shows "Switching to X for Y...". Confidence display is v2 scope.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + coverage |
| Config file | None (invoked via command line flags) |
| Quick run command | `python -m pytest tests/unit/test_vram.py tests/unit/test_intent.py -x -q` |
| Full suite command | `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ROUTE-01 | Intent->model mapping selects correct model for each intent | unit | `python -m pytest tests/unit/test_routing.py::test_intent_model_map -x` | Wave 0 |
| ROUTE-01 | Routing triggers _ensure_model_ready when model differs | unit | `python -m pytest tests/unit/test_routing.py::test_route_switches_model -x` | Wave 0 |
| ROUTE-01 | No switch when already on correct model | unit | `python -m pytest tests/unit/test_routing.py::test_no_switch_same_model -x` | Wave 0 |
| ROUTE-01 | No switch when confidence < 0.8 | unit | `python -m pytest tests/unit/test_routing.py::test_no_switch_low_confidence -x` | Wave 0 |
| ROUTE-01 | No routing when intent_enabled is False | unit | `python -m pytest tests/unit/test_routing.py::test_no_route_disabled -x` | Wave 0 |
| ROUTE-02 | Confirmation message printed before switch | unit | `python -m pytest tests/unit/test_routing.py::test_confirmation_message -x` | Wave 0 |
| ROUTE-02 | No confirmation when no switch needed | unit | `python -m pytest tests/unit/test_routing.py::test_no_confirmation_same_model -x` | Wave 0 |
| ROUTE-03 | Spinner displayed during model warmup | unit | `python -m pytest tests/unit/test_routing.py::test_spinner_during_warmup -x` | Existing (warmup_ollama_model already uses spinner) |
| ROUTE-03 | Progress bar displayed during model pull | unit | `python -m pytest tests/unit/test_routing.py::test_progress_bar_during_pull -x` | Wave 0 |
| ROUTE-01 | Non-model intents (image_gen etc.) skip routing | unit | `python -m pytest tests/unit/test_routing.py::test_skip_non_model_intents -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/test_routing.py tests/unit/test_vram.py tests/unit/test_intent.py -x -q`
- **Per wave merge:** `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_routing.py` -- covers ROUTE-01, ROUTE-02, ROUTE-03
- [ ] `tests/conftest.py` update -- add routing-specific fixtures if needed (may just extend mock_session_state)

## Sources

### Primary (HIGH confidence)
- `clod.py` lines 62-100 -- existing model constants (PIPELINE_CONFIGS, VRAM_TIERS)
- `clod.py` lines 434-516 -- existing ollama_pull, ensure_ollama_model, warmup_ollama_model
- `clod.py` lines 556-661 -- existing VRAM management (_unload, _verify, _ensure_model_ready)
- `clod.py` lines 2990-3035 -- REPL loop with Phase 2 classification hook
- `clod.py` lines 2359-2383 -- /model handler with intent_enabled=False
- `intent.py` lines 25-33 -- INTENTS tuple (7 intents)
- `intent.py` lines 228-249 -- classify_intent() public API
- Rich library -- `console.status()` and `rich.progress.Progress` are standard Rich APIs

### Secondary (MEDIUM confidence)
- REQUIREMENTS.md ROUTE-01/02/03 -- requirement definitions
- Phase 2 summaries (02-01, 02-02) -- session state fields, classification behavior

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new libraries needed, all existing
- Architecture: HIGH - clear wiring pattern, all building blocks exist
- Pitfalls: HIGH - identified from direct code reading, concrete scenarios

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable -- internal project, no external API changes expected)
