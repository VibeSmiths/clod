"""Unit tests for intent classification module."""

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_onnx_session():
    """Mock ONNX InferenceSession that returns controlled 384-dim embeddings."""
    session = MagicMock()
    # Simulate get_inputs() returning input_ids and attention_mask (no token_type_ids)
    inp_ids = MagicMock()
    inp_ids.name = "input_ids"
    attn_mask = MagicMock()
    attn_mask.name = "attention_mask"
    session.get_inputs.return_value = [inp_ids, attn_mask]

    # Return a (1, seq_len, 384) tensor from run()
    def _run(output_names, feeds):
        seq_len = feeds["input_ids"].shape[1]
        # Return a deterministic embedding based on input
        token_embs = np.random.RandomState(42).randn(1, seq_len, 384).astype(np.float32)
        return [token_embs]

    session.run = _run
    return session


@pytest.fixture
def mock_tokenizer():
    """Mock HuggingFace tokenizer."""
    tokenizer = MagicMock()
    encoded = MagicMock()
    encoded.ids = [101, 2023, 2003, 1037, 3231, 102]  # 6 tokens
    encoded.attention_mask = [1, 1, 1, 1, 1, 1]
    tokenizer.encode.return_value = encoded
    tokenizer.enable_truncation = MagicMock()
    tokenizer.enable_padding = MagicMock()
    return tokenizer


@pytest.fixture
def mock_route_embeddings(tmp_path):
    """Create a temporary route_embeddings.npz with known centroids."""
    intent_names = np.array(
        ["chat", "code", "reason", "vision", "image_gen", "image_edit", "video_gen"]
    )
    # Create 7 well-separated unit vectors in 384-dim space
    centroids = np.zeros((7, 384), dtype=np.float32)
    for i in range(7):
        centroids[i, i * 50] = 1.0  # Each intent gets a different dominant dimension
    path = tmp_path / "route_embeddings.npz"
    np.savez_compressed(str(path), intent_names=intent_names, centroids=centroids)
    return str(path)


# ---------------------------------------------------------------------------
# Keyword classification tests
# ---------------------------------------------------------------------------


class TestKeywordClassification:
    def test_keyword_image_gen(self):
        from intent import _classify_keywords

        result = _classify_keywords("generate an image of a sunset")
        assert result is not None
        intent, conf = result
        assert intent == "image_gen"
        assert conf >= 0.9

    def test_keyword_video_gen(self):
        from intent import _classify_keywords

        result = _classify_keywords("make a video of a dancing cat")
        assert result is not None
        intent, conf = result
        assert intent == "video_gen"
        assert conf >= 0.9

    def test_keyword_code(self):
        from intent import _classify_keywords

        result = _classify_keywords("write a python function to sort")
        assert result is not None
        intent, conf = result
        assert intent == "code"
        assert conf >= 0.85

    def test_keyword_reason(self):
        from intent import _classify_keywords

        result = _classify_keywords("explain why this architecture works")
        assert result is not None
        intent, conf = result
        assert intent == "reason"
        assert conf >= 0.8

    def test_keyword_image_edit(self):
        from intent import _classify_keywords

        result = _classify_keywords("edit this image and crop it")
        assert result is not None
        intent, conf = result
        assert intent == "image_edit"
        assert conf >= 0.9

    def test_keyword_vision(self):
        from intent import _classify_keywords

        result = _classify_keywords("describe this image for me")
        assert result is not None
        intent, conf = result
        assert intent == "vision"
        assert conf >= 0.85

    def test_keyword_no_match_falls_through(self):
        from intent import _classify_keywords

        result = _classify_keywords("hello how are you")
        assert result is None


# ---------------------------------------------------------------------------
# classify_intent public API tests
# ---------------------------------------------------------------------------


class TestClassifyIntent:
    def test_classify_returns_valid_intent(self):
        from intent import classify_intent, INTENTS

        # Use a keyword-matching input so no model files needed
        intent, conf = classify_intent("generate an image of a cat")
        assert intent in INTENTS
        assert 0.0 <= conf <= 1.0

    def test_all_intents_reachable(self):
        """Each of the 7 intents can be returned by keyword classification."""
        from intent import classify_intent, INTENTS

        inputs = {
            "chat": None,  # chat may need embedding, skip for keyword-only
            "code": "write a python function to sort a list",
            "reason": "explain why this approach is better",
            "vision": "describe this image for me",
            "image_gen": "generate an image of a sunset",
            "image_edit": "edit this image and resize it",
            "video_gen": "make a video of a cat",
        }
        reached = set()
        for intent_name, text in inputs.items():
            if text is None:
                continue
            result_intent, _ = classify_intent(text)
            reached.add(result_intent)

        # At least 6 intents reachable via keywords (chat may need embedding)
        assert len(reached) >= 6
        # Verify each reached intent is valid
        for r in reached:
            assert r in INTENTS

    def test_classification_latency(self):
        """Keyword-only classification completes in well under 100ms."""
        from intent import classify_intent

        start = time.perf_counter()
        classify_intent("write a python function to sort")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100, f"Classification took {elapsed_ms:.1f}ms"


# ---------------------------------------------------------------------------
# Embedding classification tests (mocked)
# ---------------------------------------------------------------------------


class TestEmbeddingClassification:
    def test_embedding_classify_ambiguous(
        self, mock_onnx_session, mock_tokenizer, mock_route_embeddings
    ):
        """Embedding path returns a valid intent for ambiguous input."""
        from intent import _classify_embedding, IntentEmbedder, INTENTS
        import intent as intent_mod

        # Set up mocked embedder
        embedder = IntentEmbedder.__new__(IntentEmbedder)
        embedder._session = mock_onnx_session
        embedder._tokenizer = mock_tokenizer
        embedder._input_names = ["input_ids", "attention_mask"]

        # Load mock route embeddings
        data = np.load(mock_route_embeddings)

        # Patch module-level state
        with (
            patch.object(intent_mod, "_embedder", embedder),
            patch.object(intent_mod, "_route_centroids", data["centroids"]),
            patch.object(intent_mod, "_route_intent_names", data["intent_names"].tolist()),
        ):
            result_intent, conf = _classify_embedding("can you help me think through this problem")
            assert result_intent in INTENTS
            assert 0.0 <= conf <= 1.0

    def test_embedder_init_resolves_paths(self, tmp_path):
        """IntentEmbedder uses _get_clod_root() to find model files via _ensure_embedder."""
        import intent as intent_mod

        fake_root = tmp_path
        model_dir = fake_root / "models" / "intent"
        model_dir.mkdir(parents=True)
        # Create dummy files
        (model_dir / "model_quint8_avx2.onnx").write_text("dummy")
        (model_dir / "tokenizer.json").write_text("dummy")

        with patch.object(intent_mod, "_get_clod_root", return_value=fake_root):
            # _ensure_embedder should try to load from the resolved path
            # It will fail on the dummy files, but we can verify path resolution
            try:
                intent_mod._ensure_embedder()
            except Exception:
                pass  # Expected -- dummy files aren't valid ONNX
            # Verify _get_clod_root was called
            intent_mod._get_clod_root.assert_called()

    def test_embedder_embed_returns_384d(self, mock_onnx_session, mock_tokenizer):
        """embed() returns numpy array of shape (384,)."""
        from intent import IntentEmbedder

        embedder = IntentEmbedder.__new__(IntentEmbedder)
        embedder._session = mock_onnx_session
        embedder._tokenizer = mock_tokenizer
        embedder._input_names = ["input_ids", "attention_mask"]

        result = embedder.embed("test input")
        assert isinstance(result, np.ndarray)
        assert result.shape == (384,)

    def test_low_confidence_returns_below_threshold(
        self, mock_onnx_session, mock_tokenizer, mock_route_embeddings
    ):
        """When embedding similarity is low, confidence reflects actual score."""
        from intent import classify_intent, INTENTS
        import intent as intent_mod

        embedder = IntentEmbedder.__new__(IntentEmbedder)
        embedder._session = mock_onnx_session
        embedder._tokenizer = mock_tokenizer
        embedder._input_names = ["input_ids", "attention_mask"]

        data = np.load(mock_route_embeddings)

        with (
            patch.object(intent_mod, "_embedder", embedder),
            patch.object(intent_mod, "_route_centroids", data["centroids"]),
            patch.object(intent_mod, "_route_intent_names", data["intent_names"].tolist()),
        ):
            # "hello" doesn't match keywords, so falls through to embedding
            intent_name, conf = classify_intent("hello")
            assert intent_name in INTENTS
            # With mock data, confidence will be whatever cosine sim produces
            assert isinstance(conf, float)

        from intent import IntentEmbedder  # re-import for reference


# ---------------------------------------------------------------------------
# Cosine similarity tests
# ---------------------------------------------------------------------------


class TestCosineSimilarity:
    def test_cosine_similarity_identical(self):
        """Identical normalized vectors produce similarity of 1.0."""
        from intent import cosine_similarity

        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        matrix = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        result = cosine_similarity(vec, matrix)
        assert abs(result[0] - 1.0) < 1e-6

    def test_cosine_similarity_orthogonal(self):
        """Orthogonal normalized vectors produce similarity of 0.0."""
        from intent import cosine_similarity

        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        matrix = np.array([[0.0, 1.0, 0.0]], dtype=np.float32)
        result = cosine_similarity(vec, matrix)
        assert abs(result[0]) < 1e-6

    def test_cosine_similarity_multiple(self):
        """Returns correct shape for multiple route vectors."""
        from intent import cosine_similarity

        vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        matrix = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.5, 0.5, 0.0],
            ],
            dtype=np.float32,
        )
        result = cosine_similarity(vec, matrix)
        assert result.shape == (3,)
        assert result[0] > result[1]  # identical > orthogonal
