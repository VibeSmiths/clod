# Phase 2: Intent Classification - Research

**Researched:** 2026-03-10
**Domain:** NLP intent classification, embedding-based semantic routing, keyword/regex pattern matching
**Confidence:** HIGH

## Summary

Phase 2 requires classifying user input into one of 7 intents (chat, code, reason, vision, image-gen, image-edit, video-gen) in under 100ms on CPU without any LLM call. The user has locked a hybrid architecture: keyword/regex rules for obvious cases, lightweight embedding model for ambiguous input.

The critical constraint is PyInstaller bundling -- sentence-transformers pulls in PyTorch (~1.5-1.8GB), which is unacceptable. The solution is to use a pre-exported quantized ONNX model (all-MiniLM-L6-v2 INT8 at ~23MB) loaded directly via `onnxruntime` + `tokenizers` (HuggingFace's Rust-based tokenizer, ~3.4MB wheel). This avoids PyTorch entirely while maintaining sub-20ms single-sentence inference on CPU.

For the semantic layer, we should NOT use `semantic-router` (aurelio-labs) as a dependency -- it adds unnecessary abstraction and its own dependency chain. Instead, implement a simple cosine similarity comparison against pre-computed route embeddings. The pattern is straightforward: embed the user query, compare against 5-10 seed utterances per intent, return the highest-scoring intent above the 0.8 confidence threshold.

**Primary recommendation:** Use `onnxruntime` + `tokenizers` + pre-exported quantized ONNX model (~23MB) for the embedding layer. Implement keyword rules as the fast path, embedding similarity as the fallback. Bundle model files in PyInstaller spec.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Hybrid architecture: keyword/regex rules catch obvious cases first, lightweight embedding model handles ambiguous input
- Embedding model: ~100MB class (e.g. all-mpnet-base-v2), bundled directly in PyInstaller EXE -- no first-run download
- Must meet <100ms CPU-only constraint per INTENT-02
- High confidence threshold: >0.8 to auto-classify. Below 0.8 = ask the user
- Show detected intent only when it would cause a model switch -- stay silent when staying on current model
- Debug tooling: `/intent` slash command for one-shot classification check + verbose toggle for extended debugging
- After `/model` manual switch: classification is disabled until explicitly re-enabled (e.g., `/intent auto` or new session)
- Code vs chat is context-dependent: "write a function" = code, "tell me a joke" = chat
- Reasoning uses hybrid signal: analytical framing + code context = reason
- Image generation has two sub-intents: image-gen (create new) vs image-edit (modify existing)
- Video-gen: natural language triggers like "make a video of..."

### Claude's Discretion
- Keyword layer aggressiveness and exact patterns
- Vision intent triggering logic
- Low-confidence prompt format (inline vs Rich panel)
- Whether to remember rejected intent suggestions per session
- REPL prompt format (show intent or not)
- Embedding model warm-up strategy (eager vs lazy)

### Deferred Ideas (OUT OF SCOPE)
- Image-edit sub-intent may need its own downstream handling beyond just classification -- Phase 4 or later
- Session intent memory / learning from user corrections -- ROUTE-05 is explicitly v2
- Confidence scores in confirm UX -- ROUTE-04 is explicitly v2
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INTENT-01 | User input is classified into one of 6 intents (chat, code, reason, vision, image-gen, video-gen) before routing | Hybrid keyword+embedding architecture; ONNX model for semantic similarity; route definitions with seed utterances |
| INTENT-02 | Classification completes in under 100ms without GPU usage (CPU-only) | Quantized INT8 ONNX model (~23MB) achieves ~20ms single-sentence latency on CPU; keyword layer is sub-1ms |
| INTENT-03 | User can override classification by using `/model` to manually select a model | Session state flag `intent_enabled` set False on `/model`, re-enabled via `/intent auto` |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| onnxruntime | >=1.17.0 | Run ONNX embedding model on CPU | Industry standard for CPU inference; no PyTorch dependency; 3x faster than PyTorch on CPU |
| tokenizers | >=0.20.0 | Fast tokenization for embedding model | HuggingFace's Rust-based tokenizer; 3.4MB wheel; used by ChromaDB for same purpose |
| numpy | >=1.24.0 | Cosine similarity computation | Already likely transitive dep; minimal overhead |

### Pre-exported Model Files (bundled, not pip-installed)
| File | Size | Purpose |
|------|------|---------|
| model_qint8_avx2.onnx | ~23 MB | Quantized INT8 embedding model (Windows AVX2) |
| tokenizer.json | ~466 KB | Fast tokenizer vocabulary and config |
| route_embeddings.npz | ~50 KB (est.) | Pre-computed embeddings for seed utterances |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| onnxruntime + tokenizers | sentence-transformers | Pulls PyTorch (~1.5GB); PyInstaller exe balloons from ~50MB to ~1.8GB |
| onnxruntime + tokenizers | semantic-router (aurelio-labs) | Adds unnecessary abstraction; still needs encoder underneath; extra dependency chain |
| onnxruntime + tokenizers | fastembed (Qdrant) | Lighter than sentence-transformers but still heavier than raw ONNX; downloads models at runtime |
| Custom cosine similarity | scikit-learn | sklearn is ~30MB+ for one function; numpy cosine is 3 lines |
| all-MiniLM-L6-v2 (23MB quantized) | all-mpnet-base-v2 (~100MB) | User suggested mpnet but MiniLM is 5x faster, 4x smaller, and sufficient for 7-class intent classification |

**Note on model choice:** The user suggested all-mpnet-base-v2 (~100MB class). all-MiniLM-L6-v2 quantized is 23MB, 5x faster on CPU (~20ms vs ~100ms), and produces 384-dim embeddings perfectly adequate for distinguishing 7 intents. Recommend MiniLM unless testing shows insufficient discrimination. The user constraint says "~100MB class" so either model satisfies the spirit of the requirement.

**Installation:**
```bash
pip install onnxruntime tokenizers numpy
```

**PyInstaller bundling additions to clod.spec:**
```python
# Intent classification model files
intent_model_datas = [
    ('models/intent/model_qint8_avx2.onnx', 'models/intent'),
    ('models/intent/tokenizer.json', 'models/intent'),
    ('models/intent/route_embeddings.npz', 'models/intent'),
]
```

## Architecture Patterns

### Recommended Project Structure
```
clod.py                          # Main file (existing)
intent.py                        # NEW: Intent classification module
models/
  intent/
    model_qint8_avx2.onnx       # Quantized ONNX embedding model
    tokenizer.json               # HuggingFace fast tokenizer config
    route_embeddings.npz         # Pre-computed intent route embeddings
    build_routes.py              # Script to generate route_embeddings.npz
tests/
  unit/
    test_intent.py               # Intent classification tests
```

### Pattern 1: Two-Layer Classification Pipeline
**What:** Keyword rules run first (sub-1ms). If no high-confidence keyword match, fall through to embedding similarity.
**When to use:** Every user input that isn't a slash command.
**Example:**
```python
# intent.py

import re
from typing import Optional, Tuple

# ── Intent Constants ──────────────────────────────────────────────────────────

INTENTS = ("chat", "code", "reason", "vision", "image_gen", "image_edit", "video_gen")

# ── Layer 1: Keyword/Regex Rules ─────────────────────────────────────────────

_KEYWORD_RULES: list[tuple[str, re.Pattern, float]] = [
    # (intent, compiled_pattern, confidence)
    ("image_gen", re.compile(
        r"\b(generate|create|make|draw|paint|design)\b.{0,30}\b(image|picture|photo|illustration|art|icon)\b",
        re.IGNORECASE), 0.95),
    ("image_edit", re.compile(
        r"\b(edit|modify|change|alter|adjust|crop|resize)\b.{0,30}\b(image|picture|photo)\b",
        re.IGNORECASE), 0.95),
    ("video_gen", re.compile(
        r"\b(generate|create|make)\b.{0,30}\b(video|animation|clip|movie)\b",
        re.IGNORECASE), 0.95),
    ("code", re.compile(
        r"\b(write|implement|code|debug|fix|refactor)\b.{0,20}\b(function|class|method|code|script|program|api)\b",
        re.IGNORECASE), 0.90),
    ("reason", re.compile(
        r"\b(explain\s+why|analyze|compare|evaluate|what\s+are\s+the\s+pros|trade.?offs?)\b",
        re.IGNORECASE), 0.85),
    ("vision", re.compile(
        r"\b(describe|look\s+at|what.s\s+in|read|ocr|scan)\b.{0,20}\b(image|picture|photo|screenshot|screen)\b",
        re.IGNORECASE), 0.90),
]

def _classify_keywords(text: str) -> Optional[Tuple[str, float]]:
    """Layer 1: Fast keyword/regex classification. Returns (intent, confidence) or None."""
    for intent, pattern, confidence in _KEYWORD_RULES:
        if pattern.search(text):
            return (intent, confidence)
    return None

# ── Layer 2: Embedding Similarity ────────────────────────────────────────────

def _classify_embedding(text: str) -> Tuple[str, float]:
    """Layer 2: Semantic similarity against route embeddings."""
    query_emb = _embed(text)  # shape: (384,)
    # Cosine similarity against pre-computed route centroids
    similarities = _cosine_similarity(query_emb, _route_embeddings)
    best_idx = similarities.argmax()
    return (INTENTS[best_idx], float(similarities[best_idx]))

# ── Public API ───────────────────────────────────────────────────────────────

def classify_intent(text: str, threshold: float = 0.8) -> Tuple[str, float]:
    """Classify user input into an intent.
    Returns (intent, confidence). If below threshold, returns ("chat", confidence).
    """
    # Layer 1: keyword rules (fast path)
    kw_result = _classify_keywords(text)
    if kw_result and kw_result[1] >= threshold:
        return kw_result

    # Layer 2: embedding similarity (slow path, still <100ms)
    intent, confidence = _classify_embedding(text)
    if confidence >= threshold:
        return (intent, confidence)

    # Below threshold: default to chat (caller should prompt user)
    return (intent, confidence)
```

### Pattern 2: ONNX Embedding Without PyTorch
**What:** Load ONNX model + tokenizer directly, perform mean pooling and normalization manually.
**When to use:** Producing embeddings for the similarity layer.
**Example:**
```python
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

class IntentEmbedder:
    """Lightweight ONNX-based text embedder. No PyTorch required."""

    def __init__(self, model_path: str, tokenizer_path: str):
        self._tokenizer = Tokenizer.from_file(tokenizer_path)
        self._tokenizer.enable_truncation(max_length=256)
        self._tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self._session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
        )

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns (384,) float32 array."""
        encoded = self._tokenizer.encode(text)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)
        # token_type_ids may be needed for some models
        token_type_ids = np.zeros_like(input_ids)

        outputs = self._session.run(
            None,
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "token_type_ids": token_type_ids,
            },
        )
        # outputs[0] shape: (1, seq_len, 384) -- token embeddings
        token_embs = outputs[0]
        # Mean pooling over non-padding tokens
        mask_expanded = attention_mask[:, :, np.newaxis].astype(np.float32)
        summed = (token_embs * mask_expanded).sum(axis=1)
        counts = mask_expanded.sum(axis=1).clip(min=1e-9)
        mean_pooled = summed / counts
        # L2 normalize
        norm = np.linalg.norm(mean_pooled, axis=1, keepdims=True).clip(min=1e-9)
        return (mean_pooled / norm).squeeze(0)
```

### Pattern 3: Session State Integration
**What:** Extend session_state with intent classification fields; disable on `/model`.
**When to use:** REPL loop integration.
**Example:**
```python
# In run_repl(), extend session_state:
session_state = {
    # ... existing fields ...
    "intent_enabled": True,      # False after /model, True after /intent auto
    "last_intent": None,         # Last classified intent string
    "last_confidence": 0.0,      # Last confidence score
}

# In REPL loop, between user_input and infer():
if session_state["intent_enabled"]:
    intent, confidence = classify_intent(user_input)
    session_state["last_intent"] = intent
    session_state["last_confidence"] = confidence
    if confidence < 0.8:
        # Prompt user (Claude's discretion on format)
        pass

# In handle_slash() for /model:
elif verb == "/model":
    # ... existing logic ...
    session_state["intent_enabled"] = False
    console.print("[dim]Intent auto-classification disabled. Use /intent auto to re-enable.[/dim]")
```

### Pattern 4: Route Embedding Pre-computation
**What:** Pre-compute and store embeddings for seed utterances, load at startup.
**When to use:** Build step (run once), load at runtime.
**Example:**
```python
# models/intent/build_routes.py -- run once to generate route_embeddings.npz
ROUTES = {
    "chat": [
        "tell me a joke", "how are you", "what's up", "hello",
        "thanks", "good morning", "let's chat",
    ],
    "code": [
        "write a python function", "implement a class",
        "debug this code", "refactor the login module",
        "fix the bug in", "create a REST API",
    ],
    "reason": [
        "explain why this happens", "analyze the tradeoffs",
        "compare these approaches", "what are the pros and cons",
        "evaluate this architecture", "why does this work",
    ],
    "vision": [
        "what's in this image", "describe this picture",
        "read the text in this screenshot", "look at this photo",
        "what do you see", "OCR this document",
    ],
    "image_gen": [
        "generate an image of", "create a picture of",
        "make me an illustration", "draw a portrait",
        "paint a landscape", "design an icon",
    ],
    "image_edit": [
        "edit this image", "modify the colors",
        "crop and resize", "change the background",
        "adjust the brightness", "remove the watermark",
    ],
    "video_gen": [
        "make a video of", "generate a video",
        "create an animation of", "produce a video clip",
    ],
}
# Embed all utterances, compute centroid per intent, save as .npz
```

### Anti-Patterns to Avoid
- **Loading PyTorch for embeddings:** The exe would balloon from ~50MB to ~1.8GB. Use ONNX runtime only.
- **Downloading models at runtime:** User explicitly requires bundled-in-exe. No first-run downloads.
- **Using an LLM for classification:** Violates the <100ms CPU-only constraint. Even a tiny LLM takes seconds.
- **Hardcoding model paths:** Use `_get_clod_root()` pattern (from Phase 1) to resolve paths relative to exe/repo root.
- **Blocking the REPL on model load:** Use lazy loading -- first classification pays startup cost, subsequent ones are instant.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Text tokenization | Custom tokenizer / regex split | `tokenizers` library (HuggingFace) | WordPiece/BPE tokenization has edge cases (unicode, subwords, special tokens) |
| Embedding inference | PyTorch model loading | `onnxruntime` with ONNX model | 3x faster on CPU, no PyTorch dependency, quantized model support |
| Cosine similarity | Custom distance metric | `numpy` dot product on L2-normalized vectors | Mathematically equivalent, numerically stable, vectorized |
| Model file path resolution | Hardcoded paths | `_get_clod_root()` existing pattern | Already handles frozen exe vs repo root distinction |

**Key insight:** The entire embedding pipeline (tokenize + infer + pool + normalize + compare) is ~50 lines of code with onnxruntime + tokenizers. There is no need for sentence-transformers, semantic-router, or any other high-level wrapper.

## Common Pitfalls

### Pitfall 1: PyTorch Creep via Transitive Dependencies
**What goes wrong:** Installing sentence-transformers or transformers pulls in PyTorch, adding ~1.5GB to the exe.
**Why it happens:** These libraries list torch as a hard dependency.
**How to avoid:** Only depend on `onnxruntime`, `tokenizers`, and `numpy`. Never import `torch` or `transformers`.
**Warning signs:** `pip install` output showing torch being downloaded; exe size jumping above 200MB.

### Pitfall 2: ONNX Model Missing token_type_ids Input
**What goes wrong:** Some ONNX exports of MiniLM don't include token_type_ids as an input, causing inference to fail.
**Why it happens:** Different export tools handle this differently.
**How to avoid:** Check the model's expected inputs with `session.get_inputs()` and only pass what's required.
**Warning signs:** ONNX runtime error about unexpected input names.

### Pitfall 3: Mean Pooling Without Attention Mask
**What goes wrong:** Padding tokens contribute to the embedding, corrupting similarity scores.
**Why it happens:** Simple averaging includes [PAD] token embeddings in the mean.
**How to avoid:** Always mask out padding tokens before averaging (multiply by attention_mask).
**Warning signs:** Short sentences and long sentences producing similar embeddings regardless of content.

### Pitfall 4: Model Path Resolution in Frozen Exe
**What goes wrong:** `__file__` points to a temp directory in PyInstaller frozen mode, not the exe location.
**Why it happens:** PyInstaller extracts to `sys._MEIPASS` at runtime.
**How to avoid:** Use `_get_clod_root()` which already handles this (checks `sys.executable.parent` when frozen).
**Warning signs:** FileNotFoundError for model files when running from exe.

### Pitfall 5: Keyword Rules Too Aggressive
**What goes wrong:** "Can you help me write a function to generate images?" gets classified as image_gen by keyword match, should be code.
**Why it happens:** Keyword rules match on surface patterns without understanding context.
**How to avoid:** Make keyword patterns require both action verb AND domain noun in proximity. Use word boundaries. Let ambiguous cases fall through to the embedding layer.
**Warning signs:** Users getting unexpected model switches on compound requests.

### Pitfall 6: Cold Start Latency
**What goes wrong:** First classification takes 500ms+ because ONNX session needs to initialize.
**Why it happens:** ONNX runtime compiles execution graphs on first inference.
**How to avoid:** Either eager-load on startup (adds ~200ms to boot) or lazy-load on first user input (first response is slower). User left this as Claude's discretion.
**Warning signs:** First interaction noticeably slower than subsequent ones.

## Code Examples

### Cosine Similarity with Numpy
```python
# Source: standard numpy pattern, verified against scikit-learn implementation
import numpy as np

def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a query vector and a matrix of vectors.
    Assumes both are L2-normalized. Returns shape (n_routes,).
    """
    return matrix @ query  # dot product of unit vectors = cosine similarity
```

### Route Embedding Storage Format
```python
# Save pre-computed route embeddings
import numpy as np

# centroids: dict[str, np.ndarray]  -- intent_name -> (384,) centroid vector
intent_names = list(centroids.keys())
centroid_matrix = np.stack([centroids[name] for name in intent_names])
np.savez_compressed(
    "models/intent/route_embeddings.npz",
    intent_names=np.array(intent_names),
    centroids=centroid_matrix,  # shape: (7, 384)
)

# Load at runtime
data = np.load("models/intent/route_embeddings.npz")
intent_names = data["intent_names"].tolist()
centroids = data["centroids"]  # shape: (7, 384), L2-normalized
```

### Slash Command: /intent
```python
# In handle_slash():
elif verb == "/intent":
    if arg.lower() == "auto":
        session_state["intent_enabled"] = True
        console.print("[dim]Intent auto-classification [green]enabled[/green][/dim]")
    elif arg.lower() == "verbose":
        session_state["intent_verbose"] = not session_state.get("intent_verbose", False)
        state = "enabled" if session_state["intent_verbose"] else "disabled"
        console.print(f"[dim]Intent verbose mode [bold]{state}[/bold][/dim]")
    elif arg:
        # One-shot classification check
        intent, confidence = classify_intent(arg)
        console.print(Panel(
            f"[bold]{intent}[/bold]  confidence: {confidence:.2f}",
            title="[cyan]Intent Classification[/cyan]",
            border_style="cyan",
            expand=False,
        ))
    else:
        # Show current intent state
        enabled = session_state.get("intent_enabled", True)
        last = session_state.get("last_intent", "none")
        conf = session_state.get("last_confidence", 0.0)
        console.print(
            f"[dim]Intent: [bold]{last}[/bold] ({conf:.2f}) | "
            f"Auto: {'on' if enabled else 'off'}[/dim]"
        )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sentence-transformers + PyTorch | ONNX Runtime + tokenizers | 2024 (sbert ONNX support) | 3x CPU speedup, no PyTorch dep |
| Float32 ONNX models | INT8 quantized ONNX | 2024 | 75% size reduction (90MB to 23MB), faster CPU inference |
| all-mpnet-base-v2 (best quality) | all-MiniLM-L6-v2 (best speed/quality) | Ongoing | 5x faster, adequate for coarse intent classification |
| scikit-learn cosine similarity | numpy dot product on normalized vectors | Always | Same result, no sklearn dependency |

**Deprecated/outdated:**
- `semantic-router` (aurelio-labs): Still works but adds unnecessary abstraction for our simple use case
- ChromaDB's built-in ONNX embedder: Designed for ChromaDB integration, not standalone use

## Open Questions

1. **AVX2 vs AVX512 quantized model**
   - What we know: Windows with modern Intel/AMD CPUs support AVX2. AVX512 is not universal.
   - What's unclear: Whether the user's CPU supports AVX512 VNNI for the more optimized model.
   - Recommendation: Ship `model_quint8_avx2.onnx` (23MB) as the default; it works on all modern x86 CPUs.

2. **Centroid vs All-Utterances Comparison**
   - What we know: Centroid (mean of seed utterances) is faster (7 comparisons). All-utterances is more accurate but slower (~50 comparisons).
   - What's unclear: Whether centroid discrimination is sufficient for 7 intents.
   - Recommendation: Start with centroids. If testing shows poor discrimination, switch to top-K nearest utterance voting. Both are well under 100ms.

3. **Image Attachment Detection for Vision Intent**
   - What we know: User left vision triggering as Claude's discretion.
   - What's unclear: How image attachments are represented in the current message flow (file paths? base64?).
   - Recommendation: Check for image file path patterns in user input as an additional signal for vision intent.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + coverage |
| Config file | none -- uses CLI args per MEMORY.md |
| Quick run command | `python -m pytest tests/unit/test_intent.py -x -q` |
| Full suite command | `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INTENT-01 | Every input classified into one of 7 intents | unit | `python -m pytest tests/unit/test_intent.py::test_classify_all_intents -x` | No -- Wave 0 |
| INTENT-01 | Keyword layer catches obvious cases | unit | `python -m pytest tests/unit/test_intent.py::test_keyword_classification -x` | No -- Wave 0 |
| INTENT-01 | Embedding layer handles ambiguous input | unit | `python -m pytest tests/unit/test_intent.py::test_embedding_classification -x` | No -- Wave 0 |
| INTENT-02 | Classification completes in under 100ms | unit | `python -m pytest tests/unit/test_intent.py::test_classification_latency -x` | No -- Wave 0 |
| INTENT-03 | /model disables intent classification | unit | `python -m pytest tests/unit/test_intent.py::test_model_override_disables_intent -x` | No -- Wave 0 |
| INTENT-03 | /intent auto re-enables classification | unit | `python -m pytest tests/unit/test_intent.py::test_intent_auto_reenables -x` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/unit/test_intent.py -x -q`
- **Per wave merge:** `python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_intent.py` -- covers INTENT-01, INTENT-02, INTENT-03
- [ ] `models/intent/` directory with model files -- needed for embedding tests
- [ ] Mock/fixture for ONNX session -- avoid requiring real model files in CI
- [ ] Framework install: `pip install onnxruntime tokenizers` -- new dependencies

## Sources

### Primary (HIGH confidence)
- [sentence-transformers/all-MiniLM-L6-v2 HuggingFace](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) - model specs, file sizes, ONNX variants
- [Sentence Transformers ONNX efficiency docs](https://sbert.net/docs/sentence_transformer/usage/efficiency.html) - ONNX backend, quantization, benchmarks
- [sentence-transformers/all-MiniLM-L6-v2/tree/main/onnx](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/main/onnx) - quantized model file sizes (23MB INT8)
- [chroma-core/onnx-embedding](https://github.com/chroma-core/onnx-embedding) - reference implementation of ONNX + tokenizers approach

### Secondary (MEDIUM confidence)
- [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router) - route-based classification pattern (informed architecture, not used as dependency)
- [aurelio-labs semantic-router quickstart](https://docs.aurelio.ai/semantic-router/get-started/quickstart) - route definition pattern with seed utterances
- [PyInstaller + sentence-transformers issues](https://github.com/huggingface/sentence-transformers/issues/1890) - confirms PyTorch bloat problem (~1.8GB exe)
- [HuggingFace tokenizers PyPI](https://pypi.org/project/tokenizers/) - package size (~3.4MB wheel)

### Tertiary (LOW confidence)
- [FastEmbed by Qdrant](https://github.com/qdrant/fastembed) - alternative lightweight embedding library (not recommended but viable fallback)
- CPU latency benchmarks (~20ms single sentence for MiniLM-L6-v2) - from multiple sources but no single authoritative benchmark

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - onnxruntime + tokenizers is the established pattern for PyTorch-free inference; ChromaDB uses identical approach
- Architecture: HIGH - hybrid keyword+embedding is well-established for intent classification; cosine similarity routing is the core of semantic-router
- Pitfalls: HIGH - PyInstaller + PyTorch bloat is extensively documented; ONNX mean pooling issues are well-known

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable domain, models rarely change)
