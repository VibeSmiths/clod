"""Build route centroid embeddings for intent classification.

Run once to generate ``route_embeddings.npz``::

    python models/intent/build_routes.py

Requires a working ONNX model and tokenizer in ``models/intent/``.
"""

from __future__ import annotations

import pathlib
import sys

import numpy as np

# -- Seed utterances per intent ----------------------------------------------

ROUTES: dict[str, list[str]] = {
    "chat": [
        "tell me a joke",
        "how are you",
        "what's up",
        "hello",
        "thanks",
        "good morning",
        "let's chat",
        "what do you think",
    ],
    "code": [
        "write a python function",
        "implement a class",
        "debug this code",
        "refactor the login module",
        "fix the bug in",
        "create a REST API",
        "add error handling to this function",
    ],
    "reason": [
        "explain why this happens",
        "analyze the tradeoffs",
        "compare these approaches",
        "what are the pros and cons",
        "evaluate this architecture",
        "why does this work",
        "break down the reasoning behind",
    ],
    "vision": [
        "what's in this image",
        "describe this picture",
        "read the text in this screenshot",
        "look at this photo",
        "what do you see",
        "OCR this document",
    ],
    "image_gen": [
        "generate an image of",
        "create a picture of",
        "make me an illustration",
        "draw a portrait",
        "paint a landscape",
        "design an icon",
    ],
    "image_edit": [
        "edit this image",
        "modify the colors",
        "crop and resize",
        "change the background",
        "adjust the brightness",
        "remove the watermark",
    ],
    "video_gen": [
        "make a video of",
        "generate a video",
        "create an animation of",
        "produce a video clip",
    ],
}


def build_centroids(embedder, routes: dict[str, list[str]], output_path: str) -> None:
    """Embed all seed utterances, compute per-intent centroid, save as .npz.

    Centroids are L2-normalized after averaging (Pitfall 7: mean of unit
    vectors is not necessarily a unit vector).
    """
    intent_names = list(routes.keys())
    centroids = []

    for intent in intent_names:
        utterance_embs = np.stack([embedder.embed(u) for u in routes[intent]])
        centroid = utterance_embs.mean(axis=0)
        # Re-normalize centroid after averaging
        norm = np.linalg.norm(centroid)
        centroid = centroid / max(norm, 1e-9)
        centroids.append(centroid)

    centroid_matrix = np.stack(centroids)  # shape: (7, 384)
    np.savez_compressed(
        output_path,
        intent_names=np.array(intent_names),
        centroids=centroid_matrix,
    )
    print(f"Saved {len(intent_names)} intent centroids to {output_path}")
    print(f"  Shape: {centroid_matrix.shape}")
    for i, name in enumerate(intent_names):
        norm_val = np.linalg.norm(centroid_matrix[i])
        print(f"  {name}: norm={norm_val:.6f}")


if __name__ == "__main__":
    # Resolve paths relative to this script's location
    script_dir = pathlib.Path(__file__).parent
    model_path = str(script_dir / "model_quint8_avx2.onnx")
    tokenizer_path = str(script_dir / "tokenizer.json")
    output_path = str(script_dir / "route_embeddings.npz")

    # Add parent dir to sys.path so we can import intent module
    parent_dir = str(script_dir.parent.parent)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    from intent import IntentEmbedder

    print("Loading ONNX model and tokenizer...")
    embedder = IntentEmbedder(model_path, tokenizer_path)

    print("Building route centroids...")
    build_centroids(embedder, ROUTES, output_path)
    print("Done.")
