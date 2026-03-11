"""Intent classification module -- two-layer pipeline.

Layer 1: Keyword/regex rules (sub-1ms, high confidence).
Layer 2: ONNX embedding similarity against route centroids (<100ms CPU).

Usage::

    from intent import classify_intent, INTENTS

    intent, confidence = classify_intent("generate an image of a sunset")
    # ("image_gen", 0.95)
"""

from __future__ import annotations

import pathlib
import re
import sys
from typing import Optional, Tuple

import numpy as np

# -- Intent Constants --------------------------------------------------------

INTENTS: Tuple[str, ...] = (
    "chat",
    "code",
    "reason",
    "vision",
    "image_gen",
    "image_edit",
    "video_gen",
)

# -- Layer 1: Keyword/Regex Rules -------------------------------------------

_KEYWORD_RULES: list[tuple[str, re.Pattern, float]] = [
    # More specific intents first to avoid false matches on compound requests.
    # Each rule: (intent, compiled_pattern, confidence)
    (
        "image_gen",
        re.compile(
            r"\b(generate|create|make|draw|paint|design)\b"
            r".{0,30}"
            r"\b(image|picture|photo|illustration|art|icon|artwork)\b",
            re.IGNORECASE,
        ),
        0.95,
    ),
    (
        "image_edit",
        re.compile(
            r"\b(edit|modify|change|alter|adjust|crop|resize|remove|replace)\b"
            r".{0,30}"
            r"\b(image|picture|photo|background|watermark)\b",
            re.IGNORECASE,
        ),
        0.95,
    ),
    (
        "video_gen",
        re.compile(
            r"\b(generate|create|make|produce)\b" r".{0,30}" r"\b(video|animation|clip|movie)\b",
            re.IGNORECASE,
        ),
        0.95,
    ),
    (
        "vision",
        re.compile(
            r"\b(describe|look\s+at|what.s\s+in|read|ocr|scan)\b"
            r".{0,20}"
            r"\b(image|picture|photo|screenshot|screen|document)\b",
            re.IGNORECASE,
        ),
        0.90,
    ),
    (
        "code",
        re.compile(
            r"\b(write|implement|code|debug|fix|refactor|create)\b"
            r".{0,20}"
            r"\b(function|class|method|code|script|program|api|module|test)\b",
            re.IGNORECASE,
        ),
        0.90,
    ),
    (
        "reason",
        re.compile(
            r"\b(explain\s+why|analyze|compare|evaluate"
            r"|what\s+are\s+the\s+pros|trade.?offs?|break\s+down)\b",
            re.IGNORECASE,
        ),
        0.85,
    ),
]


def _classify_keywords(text: str) -> Optional[Tuple[str, float]]:
    """Layer 1: Fast keyword/regex classification.

    Returns ``(intent, confidence)`` or ``None`` if no pattern matches.
    """
    for intent, pattern, confidence in _KEYWORD_RULES:
        if pattern.search(text):
            return (intent, confidence)
    return None


# -- Layer 2: ONNX Embedding Similarity -------------------------------------


def _get_clod_root() -> pathlib.Path:
    """Import helper -- avoids circular import with clod.py."""
    try:
        from clod import _get_clod_root as _root_fn

        return _root_fn()
    except ImportError:
        # Fallback: use this file's directory (intent.py sits beside clod.py)
        if getattr(sys, "frozen", False):
            return pathlib.Path(sys.executable).parent
        return pathlib.Path(__file__).parent


class IntentEmbedder:
    """Lightweight ONNX-based text embedder. No PyTorch required."""

    def __init__(self, model_path: str, tokenizer_path: str) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

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


# -- Lazy-loaded module state ------------------------------------------------

_embedder: Optional[IntentEmbedder] = None
_route_centroids: Optional[np.ndarray] = None
_route_intent_names: Optional[list[str]] = None


def _resolve_model_dir() -> pathlib.Path:
    """Find the intent model directory, checking PyInstaller bundle first.

    PyInstaller extracts data files to sys._MEIPASS (a temp dir), not to
    the exe's parent directory.  Check _MEIPASS first so bundled model
    files are found without duplicating them beside the exe.
    """
    if getattr(sys, "frozen", False):
        meipass = pathlib.Path(sys._MEIPASS) / "models" / "intent"
        if meipass.exists():
            return meipass
    return _get_clod_root() / "models" / "intent"


def _ensure_embedder() -> None:
    """Initialize the embedder and load route centroids on first call."""
    global _embedder, _route_centroids, _route_intent_names

    if _embedder is not None:
        return

    model_dir = _resolve_model_dir()

    model_path = str(model_dir / "model_quint8_avx2.onnx")
    tokenizer_path = str(model_dir / "tokenizer.json")
    routes_path = str(model_dir / "route_embeddings.npz")

    _embedder = IntentEmbedder(model_path, tokenizer_path)

    data = np.load(routes_path)
    _route_intent_names = data["intent_names"].tolist()
    _route_centroids = data["centroids"]


# -- Cosine Similarity -------------------------------------------------------


def cosine_similarity(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a query vector and a matrix of vectors.

    Assumes both are L2-normalized. Returns shape ``(n_routes,)``.
    """
    return matrix @ query


# -- Layer 2: Embedding Classification ---------------------------------------


def _classify_embedding(text: str) -> Tuple[str, float]:
    """Layer 2: Semantic similarity against route centroids."""
    assert _embedder is not None, "Embedder not initialized -- call _ensure_embedder()"
    assert _route_centroids is not None
    assert _route_intent_names is not None

    query_emb = _embedder.embed(text)
    similarities = cosine_similarity(query_emb, _route_centroids)
    best_idx = int(similarities.argmax())
    return (_route_intent_names[best_idx], float(similarities[best_idx]))


# -- Public API --------------------------------------------------------------


def classify_intent(text: str, threshold: float = 0.8) -> Tuple[str, float]:
    """Classify user input into an intent.

    Returns ``(intent, confidence)``. If confidence is below *threshold*,
    the caller should prompt the user for clarification.
    """
    # Layer 1: keyword rules (fast path)
    kw_result = _classify_keywords(text)
    if kw_result is not None and kw_result[1] >= threshold:
        return kw_result

    # Layer 2: embedding similarity (slow path, still <100ms)
    try:
        _ensure_embedder()
        intent, confidence = _classify_embedding(text)
        return (intent, confidence)
    except Exception:
        # If embedding layer fails (missing model files, etc.),
        # return keyword result if available, else default to chat
        if kw_result is not None:
            return kw_result
        return ("chat", 0.0)
