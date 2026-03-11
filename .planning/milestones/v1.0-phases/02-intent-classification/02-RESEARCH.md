# Phase 2: Intent Classification - Research

**Researched:** 2026-03-10 (re-researched)
**Domain:** NLP intent classification, embedding-based semantic routing, keyword/regex pattern matching
**Confidence:** HIGH

## Summary

Phase 2 requires classifying user input into one of 7 intents (chat, code, reason, vision, image-gen, image-edit, video-gen) in under 100ms on CPU without any LLM call. The user has locked a hybrid architecture: keyword/regex rules for obvious cases, lightweight embedding model for ambiguous input.

The critical constraint is PyInstaller bundling -- sentence-transformers pulls in PyTorch (~1.5-1.8GB), which is unacceptable. The solution is to use a pre-exported quantized ONNX model loaded directly via `onnxruntime` + `tokenizers` (HuggingFace's Rust-based tokenizer, ~3.4MB wheel). This avoids PyTorch entirely while maintaining sub-20ms single-sentence inference on CPU.

**IMPORTANT CORRECTION from previous research:** The AVX2-compatible quantized model file is `model_quint8_avx2.onnx` (UNSIGNED int8), NOT `model_qint8_avx2.onnx`. The signed int8 variants (`model_qint8_*`) are only for AVX512/VNNI CPUs. Using the wrong quantization format on AVX2 causes incorrect predictions due to saturation in the VPMADDUBSW instruction. This was a confirmed onnxruntime bug (issue #6004, resolved by using unsigned int8 for AVX2).

For the semantic layer, implement a simple cosine similarity comparison against pre-computed route centroids. The pattern is: embed the user query, compare against 7 intent centroids (mean of 5-10 seed utterances per intent), return the highest-scoring intent above the 0.8 confidence threshold. Centroid comparison is sufficient for 7 well-separated intents and keeps comparison count minimal.

**Primary recommendation:** Use `onnxruntime` + `tokenizers` + `model_quint8_avx2.onnx` (23MB, unsigned int8) for the embedding layer. Implement keyword rules as the fast path, embedding similarity as the fallback. Bundle model files in PyInstaller spec.

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
| INTENT-01 | User input is classified into one of 6 intents (chat, code, reason, vision, image-gen, video-gen) before routing | Hybrid keyword+embedding architecture; ONNX model for semantic similarity; 7 route definitions (6 + image-edit sub-intent) with seed utterances; centroid-based comparison |
| INTENT-02 | Classification completes in under 100ms without GPU usage (CPU-only) | Quantized UINT8 ONNX model (model_quint8_avx2.onnx, 23MB) achieves ~20ms single-sentence latency on CPU; keyword layer is sub-1ms; centroid comparison is 7 dot products |
| INTENT-03 | User can override classification by using `/model` to manually select a model | Session state flag `intent_enabled` set False on `/model`, re-enabled via `/intent auto`; `/intent` slash command for debug |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| onnxruntime | >=1.17.0 | Run ONNX embedding model on CPU | Industry standard for CPU inference; no PyTorch dependency; 3x faster than PyTorch on CPU |
| tokenizers | >=0.20.0 | Fast tokenization for embedding model | HuggingFace's Rust-based tokenizer; 3.4MB wheel; used by ChromaDB for same purpose |
| numpy | >=1.24.0 | Cosine similarity computation | Already likely transitive dep; minimal overhead |

### Pre-exported Model Files (bundled, not pip-installed)
| File | Size | Purpose | Source |
|------|------|---------|--------|
| model_quint8_avx2.onnx | ~23 MB | Quantized UINT8 embedding model (AVX2 compatible) | [HuggingFace all-MiniLM-L6-v2/onnx](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/main/onnx) |
| tokenizer.json | ~466 KB | Fast tokenizer vocabulary and config | Same repo, root directory |
| route_embeddings.npz | ~50 KB (est.) | Pre-computed centroids for 7 intent routes | Generated by build_routes.py script |

### ONNX Model File Selection Guide (RESOLVED)

**This was an open question -- now resolved with HIGH confidence:**

The official all-MiniLM-L6-v2 repository provides these quantized ONNX variants:

| File | Quantization | Target CPU | Size |
|------|-------------|------------|------|
| model_quint8_avx2.onnx | UINT8 (unsigned) | AVX2 (most modern x86) | 23 MB |
| model_qint8_avx512.onnx | INT8 (signed) | AVX-512 only | 23 MB |
| model_qint8_avx512_vnni.onnx | INT8 (signed) | AVX-512 VNNI only | 23 MB |
| model_qint8_arm64.onnx | INT8 (signed) | ARM64 | 23 MB |

**Decision: Ship `model_quint8_avx2.onnx`** (unsigned INT8, AVX2).
- AVX2 is supported on all modern x86-64 CPUs (Intel Haswell 2013+, AMD Excavator 2015+)
- The UNSIGNED variant avoids the saturation bug in VPMADDUBSW on non-VNNI hardware (onnxruntime issue #6004)
- The signed INT8 variants (`model_qint8_*`) produce INCORRECT results on AVX2-only CPUs
- The user's machine is Windows x86-64, so AVX2 is guaranteed
- If ARM or Linux support is needed later, ship additional variants and select at runtime

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

**Model file download (one-time build step):**
```bash
# Download from HuggingFace -- run once, commit to repo
pip install huggingface-hub
python -c "
from huggingface_hub import hf_hub_download
repo = 'sentence-transformers/all-MiniLM-L6-v2'
for f in ['onnx/model_quint8_avx2.onnx', 'tokenizer.json']:
    hf_hub_download(repo, f, local_dir='models/intent')
"
# Move ONNX file out of onnx/ subfolder
mv models/intent/onnx/model_quint8_avx2.onnx models/intent/
rmdir models/intent/onnx
```

**PyInstaller bundling additions to clod.spec:**
```python
# Intent classification model files
intent_model_datas = [
    ('models/intent/model_quint8_avx2.onnx', 'models/intent'),
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
    model_quint8_avx2.onnx      # Quantized ONNX embedding model (UINT8, AVX2)
    tokenizer.json               # HuggingFace fast tokenizer config
    route_embeddings.npz         # Pre-computed intent route centroids
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
    """Layer 2: Semantic similarity against route centroids."""
    query_emb = _embed(text)  # shape: (384,)
    # Cosine similarity against pre-computed route centroids
    similarities = _cosine_similarity(query_emb, _route_centroids)
    best_idx = similarities.argmax()
    return (INTENTS[best_idx], float(similarities[best_idx]))

# ── Public API ───────────────────────────────────────────────────────────────

def classify_intent(text: str, threshold: float = 0.8) -> Tuple[str, float]:
    """Classify user input into an intent.
    Returns (intent, confidence). If below threshold, caller should prompt user.
    """
    # Layer 1: keyword rules (fast path)
    kw_result = _classify_keywords(text)
    if kw_result and kw_result[1] >= threshold:
        return kw_result

    # Layer 2: embedding similarity (slow path, still <100ms)
    intent, confidence = _classify_embedding(text)
    return (intent, confidence)
```

### Pattern 2: ONNX Embedding Without PyTorch
**What:** Load ONNX model + tokenizer directly, perform mean pooling and normalization manually.
**When to use:** Producing embeddings for the similarity layer.
**Critical detail:** The ONNX model inputs vary by export. Check `session.get_inputs()` to determine whether `token_type_ids` is required.
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
        # Detect required inputs (some ONNX exports omit token_type_ids)
        self._input_names = [inp.name for inp in self._session.get_inputs()]

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns (384,) float32 array."""
        encoded = self._tokenizer.encode(text)
        input_ids = np.array([encoded.ids], dtype=np.int64)
        attention_mask = np.array([encoded.attention_mask], dtype=np.int64)

        feeds = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }
        # Only add token_type_ids if the model expects it
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(input_ids)

        outputs = self._session.run(None, feeds)
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
**Integration point:** Between `user_input` capture (line 2940) and `infer()` call (line 2941).
**Example:**
```python
# In run_repl(), extend session_state (line 2859):
session_state = {
    # ... existing fields ...
    "intent_enabled": True,      # False after /model, True after /intent auto
    "last_intent": None,         # Last classified intent string
    "last_confidence": 0.0,      # Last confidence score
    "intent_verbose": False,     # Verbose debug mode
}

# In REPL loop, between user_input and infer() (after line 2940):
if session_state["intent_enabled"]:
    intent, confidence = classify_intent(user_input)
    session_state["last_intent"] = intent
    session_state["last_confidence"] = confidence
    if session_state.get("intent_verbose"):
        console.print(f"[dim]  intent={intent} conf={confidence:.2f}[/dim]")
    if confidence < 0.8:
        # Prompt user (Claude's discretion on format)
        pass
    # NOTE: This phase only classifies -- Phase 3 acts on the result for model routing

# In handle_slash() for /model (line 2351):
elif verb == "/model":
    # ... existing logic ...
    session_state["intent_enabled"] = False
    console.print("[dim]Intent auto-classification disabled. Use /intent auto to re-enable.[/dim]")
```

### Pattern 4: Route Embedding Pre-computation (Centroid Approach)
**What:** Pre-compute CENTROID embeddings (mean of seed utterances per intent), stored as .npz.
**When to use:** Build step (run once), load at runtime.
**Why centroids, not all-utterances (RESOLVED):**
- For 7 well-separated intent classes, centroid comparison requires only 7 dot products
- All-utterances comparison would require ~50 dot products (7 intents x ~7 utterances)
- Research confirms centroid classification achieves "decent accuracy" for well-separated classes
- Our intents ARE well-separated (chat vs code vs image-gen are semantically distant)
- If testing reveals poor discrimination on specific intent pairs (e.g., code vs reason), add more seed utterances to those specific intents rather than switching to all-utterances
**Example:**
```python
# models/intent/build_routes.py -- run once to generate route_embeddings.npz
ROUTES = {
    "chat": [
        "tell me a joke", "how are you", "what's up", "hello",
        "thanks", "good morning", "let's chat", "what do you think",
    ],
    "code": [
        "write a python function", "implement a class",
        "debug this code", "refactor the login module",
        "fix the bug in", "create a REST API",
        "add error handling to this function",
    ],
    "reason": [
        "explain why this happens", "analyze the tradeoffs",
        "compare these approaches", "what are the pros and cons",
        "evaluate this architecture", "why does this work",
        "break down the reasoning behind",
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

def build_centroids(embedder, routes, output_path):
    """Embed all seed utterances, compute per-intent centroid, save as .npz."""
    intent_names = list(routes.keys())
    centroids = []
    for intent in intent_names:
        utterance_embs = np.stack([embedder.embed(u) for u in routes[intent]])
        centroid = utterance_embs.mean(axis=0)
        # Re-normalize centroid after averaging
        centroid = centroid / np.linalg.norm(centroid).clip(min=1e-9)
        centroids.append(centroid)

    centroid_matrix = np.stack(centroids)  # shape: (7, 384)
    np.savez_compressed(
        output_path,
        intent_names=np.array(intent_names),
        centroids=centroid_matrix,
    )
```

### Pattern 5: Vision Intent Detection (RESOLVED)
**What:** How to detect vision intent given the current codebase.
**Key finding from code investigation:** The current codebase has NO image/attachment handling at all. Messages in the REPL loop are plain text strings (`{"role": "user", "content": user_input}`). Ollama's vision API expects images as base64-encoded strings in a separate `images` array on the message object -- but clod doesn't implement this yet.

**Recommendation for Phase 2:** Detect vision intent via KEYWORDS ONLY (e.g., "describe this image", "what's in this picture", "OCR this screenshot"). Do NOT attempt to detect image attachments because:
1. The codebase has no image attachment mechanism
2. Image attachment support would be a separate feature (likely Phase 4+ or a dedicated effort)
3. Keyword-based vision detection is sufficient to trigger routing to qwen2.5vl:7b

**Future consideration:** When image attachments are eventually added (e.g., drag-and-drop file paths, `/image <path>` command), the vision intent classifier should also check for the presence of image data in the message. This is out of scope for Phase 2.

### Anti-Patterns to Avoid
- **Loading PyTorch for embeddings:** The exe would balloon from ~50MB to ~1.8GB. Use ONNX runtime only.
- **Downloading models at runtime:** User explicitly requires bundled-in-exe. No first-run downloads.
- **Using an LLM for classification:** Violates the <100ms CPU-only constraint. Even a tiny LLM takes seconds.
- **Hardcoding model paths:** Use `_get_clod_root()` pattern (from Phase 1) to resolve paths relative to exe/repo root.
- **Blocking the REPL on model load:** Use lazy loading -- first classification pays startup cost, subsequent ones are instant.
- **Using signed INT8 model on AVX2 CPU:** Ship `model_quint8_avx2.onnx` (UNSIGNED), not `model_qint8_avx2.onnx` (does not exist) or `model_qint8_avx512.onnx` (wrong instruction set).
- **Passing token_type_ids without checking:** Some ONNX model exports omit this input. Always check `session.get_inputs()` first.

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

### Pitfall 2: Wrong Quantization Format for CPU Architecture
**What goes wrong:** Using a signed INT8 model (model_qint8_*) on an AVX2-only CPU produces incorrect embeddings.
**Why it happens:** Saturation in the VPMADDUBSW instruction when non-VNNI hardware processes signed INT8 values. The intermediate 16-bit accumulation overflows.
**How to avoid:** Use `model_quint8_avx2.onnx` (UNSIGNED INT8) which avoids the saturation path. The official HuggingFace repo specifically exports this variant for AVX2 compatibility.
**Warning signs:** Embeddings that produce nonsensical similarity scores; all intents scoring similarly.
**Source:** [onnxruntime issue #6004](https://github.com/microsoft/onnxruntime/issues/6004)

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

### Pitfall 7: Centroid Not Re-normalized After Averaging
**What goes wrong:** Centroid vectors are not unit-length after averaging seed utterance embeddings, making cosine similarity via dot product return incorrect values.
**Why it happens:** The mean of unit vectors is NOT necessarily a unit vector.
**How to avoid:** Always L2-normalize centroids after computing the mean of seed utterance embeddings.
**Warning signs:** Similarity scores consistently below expected range.

## Code Examples

### Cosine Similarity with Numpy
```python
# Source: standard numpy pattern
import numpy as np

def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a query vector and a matrix of vectors.
    Assumes both are L2-normalized. Returns shape (n_routes,).
    """
    return matrix @ query  # dot product of unit vectors = cosine similarity
```

### Route Embedding Storage and Loading
```python
# Save pre-computed route centroids
import numpy as np

intent_names = list(centroids.keys())
centroid_matrix = np.stack([centroids[name] for name in intent_names])
np.savez_compressed(
    "models/intent/route_embeddings.npz",
    intent_names=np.array(intent_names),
    centroids=centroid_matrix,  # shape: (7, 384), L2-normalized
)

# Load at runtime
data = np.load(route_embeddings_path)
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

### REPL Integration Point
```python
# In the REPL loop (clod.py, after line 2940 where user_input is appended to messages):
# Classification runs BEFORE infer() call

# Key insertion point in run_repl():
#   line 2931: user_input = user_input.strip()
#   line 2935: if user_input.startswith("/"): handle_slash(...)
#   line 2940: messages.append({"role": "user", "content": user_input})
#   >>> INTENT CLASSIFICATION GOES HERE <<<
#   line 2941: reply = infer(messages, session_state["model"], ...)

# Phase 2 only classifies and stores in session_state.
# Phase 3 will use session_state["last_intent"] to route to the correct model.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| sentence-transformers + PyTorch | ONNX Runtime + tokenizers | 2024 (sbert ONNX support) | 3x CPU speedup, no PyTorch dep |
| Float32 ONNX models | UINT8/INT8 quantized ONNX | 2024 | 75% size reduction (90MB to 23MB), faster CPU inference |
| all-mpnet-base-v2 (best quality) | all-MiniLM-L6-v2 (best speed/quality) | Ongoing | 5x faster, adequate for coarse intent classification |
| scikit-learn cosine similarity | numpy dot product on normalized vectors | Always | Same result, no sklearn dependency |
| Signed INT8 for all platforms | Platform-specific quantization | 2020+ | UINT8 for AVX2, INT8 for AVX512/VNNI -- avoids saturation bugs |

**Deprecated/outdated:**
- `semantic-router` (aurelio-labs): Still works but adds unnecessary abstraction for our simple use case
- ChromaDB's built-in ONNX embedder: Designed for ChromaDB integration, not standalone use

## Open Questions

All three previous open questions have been RESOLVED. No remaining open questions.

1. **~~AVX2 vs AVX512 quantized model~~** -- RESOLVED
   - Ship `model_quint8_avx2.onnx` (unsigned INT8, 23MB). See "ONNX Model File Selection Guide" above.

2. **~~Centroid vs all-utterances comparison~~** -- RESOLVED
   - Use centroids. 7 well-separated intents with 5-10 seed utterances each. Centroid comparison is 7 dot products, well under 1ms. If specific intent pairs show poor discrimination, add more seed utterances to those intents. See "Pattern 4" above.

3. **~~Image attachment detection for vision intent~~** -- RESOLVED
   - The codebase has NO image attachment mechanism. Ollama expects base64 in an `images` array on the message, but clod doesn't implement this. Use keyword-only detection for vision intent in Phase 2. See "Pattern 5" above.

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
- [sentence-transformers/all-MiniLM-L6-v2 ONNX files](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/main/onnx) - verified exact file names and sizes: model_quint8_avx2.onnx (23MB), model_qint8_avx512.onnx (23MB), model_qint8_avx512_vnni.onnx (23MB), model_qint8_arm64.onnx (23MB), model.onnx (90.4MB)
- [onnxruntime issue #6004](https://github.com/microsoft/onnxruntime/issues/6004) - confirms signed INT8 produces incorrect results on AVX2-only CPUs; resolved by using UINT8 (reduce_range) or unsigned quantization
- [onnxruntime quantization docs](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) - AVX2 recommendation: use U8U8 format; AVX512: use U8S8
- [Sentence Transformers ONNX efficiency docs](https://sbert.net/docs/sentence_transformer/usage/efficiency.html) - ONNX backend, quantization, benchmarks
- [Ollama vision docs](https://docs.ollama.com/capabilities/vision) - images sent as base64 in `images` array on message
- [Ollama API docs](https://github.com/ollama/ollama/blob/main/docs/api.md) - chat API message format with images field

### Secondary (MEDIUM confidence)
- [aurelio-labs/semantic-router](https://github.com/aurelio-labs/semantic-router) - route-based classification pattern (informed architecture, not used as dependency)
- [HuggingFace tokenizers PyPI](https://pypi.org/project/tokenizers/) - package size (~3.4MB wheel)
- Centroid vs nearest-neighbor for intent classification - multiple sources confirm centroid is adequate for well-separated classes with few-shot examples

### Tertiary (LOW confidence)
- CPU latency benchmarks (~20ms single sentence for MiniLM-L6-v2) - from multiple sources but no single authoritative benchmark on this specific hardware

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - onnxruntime + tokenizers is the established pattern for PyTorch-free inference; ChromaDB uses identical approach; file names verified on HuggingFace
- Architecture: HIGH - hybrid keyword+embedding is well-established for intent classification; centroid routing confirmed sufficient for well-separated classes
- Pitfalls: HIGH - AVX2/VNNI saturation bug verified via official onnxruntime issue; PyInstaller + PyTorch bloat extensively documented; mean pooling issues well-known
- Vision integration: HIGH - code investigation confirms no image handling exists; keyword-only approach is the correct Phase 2 scope

**Changes from previous research:**
1. CORRECTED model filename: `model_quint8_avx2.onnx` (UNSIGNED INT8), not `model_qint8_avx2.onnx` (does not exist)
2. RESOLVED centroid vs all-utterances: centroid is sufficient, with fallback strategy documented
3. RESOLVED vision intent: keyword-only detection, no image attachment support exists in codebase
4. ADDED Pitfall 7: centroid re-normalization after averaging
5. ADDED detailed model download instructions
6. ADDED IntentEmbedder input detection (check `session.get_inputs()` for token_type_ids)
7. ADDED REPL integration point with exact line numbers

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable domain, models rarely change)
