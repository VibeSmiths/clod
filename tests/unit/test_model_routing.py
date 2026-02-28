"""
Unit tests for model/adapter routing logic.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import pick_adapter, PIPELINE_CONFIGS, CLOUD_MODEL_PREFIXES


@pytest.fixture
def cfg():
    return clod.load_config()


# ── pick_adapter ───────────────────────────────────────────────────────────────


def test_pick_adapter_ollama(cfg):
    """Local (Ollama) model names route to 'ollama'."""
    assert pick_adapter("qwen2.5-coder:14b", None, cfg) == "ollama"
    assert pick_adapter("deepseek-r1:14b", None, cfg) == "ollama"
    assert pick_adapter("llama3.1:8b", None, cfg) == "ollama"


def test_pick_adapter_litellm(cfg):
    """Cloud model prefixes route to 'litellm'."""
    assert pick_adapter("claude-sonnet", None, cfg) == "litellm"
    assert pick_adapter("gpt-4o", None, cfg) == "litellm"
    assert pick_adapter("gemini-flash", None, cfg) == "litellm"
    assert pick_adapter("groq-fast", None, cfg) == "litellm"
    assert pick_adapter("o1-mini", None, cfg) == "litellm"
    assert pick_adapter("o3-large", None, cfg) == "litellm"
    assert pick_adapter("together-llama", None, cfg) == "litellm"


def test_pick_adapter_pipeline(cfg):
    """Any model with a pipeline argument routes to 'pipeline'."""
    assert pick_adapter("qwen2.5-coder:14b", "code_review", cfg) == "pipeline"
    assert pick_adapter("claude-sonnet", "reason_review", cfg) == "pipeline"
    assert pick_adapter("llama3.1:8b", "chat_assist", cfg) == "pipeline"


# ── PIPELINE_CONFIGS structure ─────────────────────────────────────────────────


def test_pipeline_configs_have_required_keys():
    """Every pipeline entry has 'local', 'claude', and 'description'."""
    for name, entry in PIPELINE_CONFIGS.items():
        assert "local" in entry, f"Pipeline '{name}' missing 'local'"
        assert "claude" in entry, f"Pipeline '{name}' missing 'claude'"
        assert "description" in entry, f"Pipeline '{name}' missing 'description'"


def test_pipeline_configs_local_models_are_ollama():
    """No pipeline's 'local' model starts with a cloud prefix."""
    for name, entry in PIPELINE_CONFIGS.items():
        local = entry["local"]
        is_cloud = any(local.startswith(p) for p in CLOUD_MODEL_PREFIXES)
        assert not is_cloud, (
            f"Pipeline '{name}' local model '{local}' looks like a cloud model"
        )


def test_pipeline_configs_claude_models_are_cloud():
    """All pipeline 'claude' values start with 'claude-'."""
    for name, entry in PIPELINE_CONFIGS.items():
        assert entry["claude"].startswith("claude-"), (
            f"Pipeline '{name}' claude value '{entry['claude']}' does not start with 'claude-'"
        )


def test_cloud_prefixes_coverage():
    """Spot-check that expected cloud prefixes exist in CLOUD_MODEL_PREFIXES."""
    expected = ("claude-", "gpt-", "gemini-", "groq-", "o1-", "o3-", "together-")
    for prefix in expected:
        assert prefix in CLOUD_MODEL_PREFIXES, (
            f"Expected cloud prefix '{prefix}' not found in CLOUD_MODEL_PREFIXES"
        )
