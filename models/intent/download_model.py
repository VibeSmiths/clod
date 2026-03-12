"""Download intent classification model files from HuggingFace.

Downloads the quantized ONNX model and tokenizer for all-MiniLM-L6-v2,
then generates route_embeddings.npz via build_routes.py.

Usage::

    python models/intent/download_model.py
"""

from __future__ import annotations

import pathlib
import sys
import urllib.request

MODEL_DIR = pathlib.Path(__file__).parent

FILES = {
    "model_quint8_avx2.onnx": (
        "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/"
        "resolve/main/onnx/model_quint8_avx2.onnx"
    ),
    "tokenizer.json": (
        "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/"
        "resolve/main/tokenizer.json"
    ),
}


def download() -> None:
    for filename, url in FILES.items():
        dest = MODEL_DIR / filename
        if dest.exists():
            print(f"  {filename} already exists, skipping")
            continue
        print(f"  Downloading {filename} ...")
        urllib.request.urlretrieve(url, dest)
        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  {filename} ({size_mb:.1f} MB)")


def build_centroids() -> None:
    npz = MODEL_DIR / "route_embeddings.npz"
    if npz.exists():
        print("  route_embeddings.npz already exists, skipping")
        return
    print("  Building route_embeddings.npz ...")
    # Add project root to path so build_routes can import intent module
    project_root = str(MODEL_DIR.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    sys.path.insert(0, str(MODEL_DIR))
    from build_routes import build_centroids as _build
    from build_routes import ROUTES
    from intent import IntentEmbedder

    model_path = str(MODEL_DIR / "model_quint8_avx2.onnx")
    tokenizer_path = str(MODEL_DIR / "tokenizer.json")
    embedder = IntentEmbedder(model_path, tokenizer_path)
    _build(embedder, ROUTES, str(npz))
    print("  route_embeddings.npz created")


if __name__ == "__main__":
    print("Fetching intent model files...")
    download()
    print("Generating centroids...")
    build_centroids()
    print("Done.")
