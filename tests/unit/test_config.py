"""
Unit tests for load_config() / save_config() round-trip.
"""

import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod


def test_load_config_returns_defaults(tmp_path, monkeypatch):
    """load_config() returns all expected keys when no config file exists."""
    monkeypatch.setattr(clod, "config_path", lambda: tmp_path / "nonexistent.json")
    cfg = clod.load_config()

    assert "ollama_url" in cfg
    assert "litellm_url" in cfg
    assert "litellm_key" in cfg
    assert "pipelines_url" in cfg
    assert "searxng_url" in cfg
    assert "default_model" in cfg
    assert "pipeline" in cfg
    assert "enable_tools" in cfg
    assert "token_budget" in cfg


def test_load_config_merges_user_file(tmp_path, monkeypatch):
    """load_config() merges user overrides over defaults."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"default_model": "llama3.1:8b", "enable_tools": True}))
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)
    cfg = clod.load_config()

    assert cfg["default_model"] == "llama3.1:8b"
    assert cfg["enable_tools"] is True
    # Default values must still be present
    assert cfg["ollama_url"] == "http://localhost:11434"


def test_save_and_reload_config(tmp_path, monkeypatch):
    """save_config() persists values that load_config() can read back."""
    cfg_file = tmp_path / "clod" / "config.json"
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)

    data = clod.load_config()
    data["default_model"] = "deepseek-r1:14b"
    clod.save_config(data)

    reloaded = clod.load_config()
    assert reloaded["default_model"] == "deepseek-r1:14b"


def test_config_has_token_budget_default(tmp_path, monkeypatch):
    """Default token_budget is 100_000."""
    monkeypatch.setattr(clod, "config_path", lambda: tmp_path / "nonexistent.json")
    cfg = clod.load_config()
    assert cfg["token_budget"] == 100_000
