"""
Tests for top-level entry points and config utilities:
  run_oneshot, main(), config_path, history_path, save_config, load_config
"""

import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod

# ── run_oneshot ───────────────────────────────────────────────────────────────


def test_run_oneshot_calls_infer(monkeypatch, fake_console, mock_cfg):
    """run_oneshot passes the prompt as the last user message to infer."""
    calls = []

    def fake_infer(messages, model, pipeline, cfg, tools_on, **kw):
        calls.append(messages[:])
        return "reply"

    monkeypatch.setattr(clod, "infer", fake_infer)
    clod.run_oneshot("hello", "model", None, None, False, mock_cfg)

    assert len(calls) == 1
    assert calls[0][-1]["content"] == "hello"
    assert calls[0][-1]["role"] == "user"


def test_run_oneshot_with_system(monkeypatch, fake_console, mock_cfg):
    """When system is provided, it becomes the first message with role='system'."""
    calls = []
    monkeypatch.setattr(clod, "infer", lambda *a, **k: (calls.append(a[0]), "")[1])
    clod.run_oneshot("hi", "m", None, "be brief", False, mock_cfg)

    assert calls[0][0]["role"] == "system"
    assert calls[0][0]["content"] == "be brief"


def test_run_oneshot_no_system(monkeypatch, fake_console, mock_cfg):
    """Without system prompt, only the user message is in the messages list."""
    calls = []
    monkeypatch.setattr(clod, "infer", lambda *a, **k: (calls.append(a[0]), "")[1])
    clod.run_oneshot("only user", "m", None, None, False, mock_cfg)

    assert len(calls[0]) == 1
    assert calls[0][0]["role"] == "user"


def test_run_oneshot_passes_model_pipeline(monkeypatch, fake_console, mock_cfg):
    """Model and pipeline arguments are forwarded to infer."""
    captured = {}
    monkeypatch.setattr(
        clod,
        "infer",
        lambda msgs, model, pipeline, cfg, tools_on, **kw: captured.update(
            {"model": model, "pipeline": pipeline}
        )
        or "",
    )
    clod.run_oneshot("q", "claude-sonnet-4-6", "code_review", None, False, mock_cfg)

    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["pipeline"] == "code_review"


def test_run_oneshot_tools_on_forwarded(monkeypatch, fake_console, mock_cfg):
    """tools_on flag is forwarded to infer."""
    captured = {}
    monkeypatch.setattr(
        clod,
        "infer",
        lambda msgs, model, pipeline, cfg, tools_on, **kw: captured.update({"tools_on": tools_on})
        or "",
    )
    clod.run_oneshot("q", "m", None, None, True, mock_cfg)
    assert captured["tools_on"] is True


# ── main() ────────────────────────────────────────────────────────────────────


def test_main_oneshot(monkeypatch, fake_console, mock_cfg):
    """main() with -p flag calls run_oneshot and exits cleanly."""
    monkeypatch.setattr(sys, "argv", ["clod", "-p", "explain quicksort"])
    monkeypatch.setattr(clod, "load_config", lambda: mock_cfg)
    monkeypatch.setattr(clod, "run_oneshot", lambda *a, **k: None)
    clod.main()  # should not raise


def test_main_oneshot_short_flag(monkeypatch, fake_console, mock_cfg):
    """main() with --print flag also triggers one-shot mode."""
    monkeypatch.setattr(sys, "argv", ["clod", "--print", "hello world"])
    monkeypatch.setattr(clod, "load_config", lambda: mock_cfg)
    monkeypatch.setattr(clod, "run_oneshot", lambda *a, **k: None)
    clod.main()


def test_main_index_invalid_dir(monkeypatch, fake_console):
    """main() with --index pointing to a non-existent dir exits with code 1."""
    monkeypatch.setattr(sys, "argv", ["clod", "--index", "/no/such/path/xyz_nonexistent"])
    monkeypatch.setattr(
        clod,
        "load_config",
        lambda: {
            "ollama_url": "http://localhost:11434",
            "litellm_url": "http://localhost:4000",
            "litellm_key": "sk-x",
            "pipelines_url": "http://localhost:9099",
            "searxng_url": "http://localhost:8080",
            "default_model": "m",
            "pipeline": None,
            "enable_tools": False,
            "token_budget": 10000,
        },
    )
    with pytest.raises(SystemExit) as exc:
        clod.main()
    assert exc.value.code == 1


def test_main_index_valid_dir(monkeypatch, fake_console, mock_cfg, tmp_path):
    """main() with --index pointing to a valid dir calls run_index_mode."""
    monkeypatch.setattr(sys, "argv", ["clod", "--index", str(tmp_path)])
    monkeypatch.setattr(clod, "load_config", lambda: mock_cfg)
    called = []
    monkeypatch.setattr(clod, "run_index_mode", lambda root, cfg: called.append(root))
    clod.main()
    assert len(called) == 1


def test_main_pipe_mode(monkeypatch, fake_console, mock_cfg):
    """main() reads from stdin when it is not a TTY."""
    import io

    monkeypatch.setattr(sys, "argv", ["clod"])
    monkeypatch.setattr(clod, "load_config", lambda: mock_cfg)
    monkeypatch.setattr(sys, "stdin", io.StringIO("pipe prompt"))
    monkeypatch.setattr(clod, "run_oneshot", lambda *a, **k: None)
    clod.main()


def test_main_pipe_mode_empty_stdin(monkeypatch, fake_console, mock_cfg):
    """main() with empty stdin does not call run_oneshot."""
    import io

    monkeypatch.setattr(sys, "argv", ["clod"])
    monkeypatch.setattr(clod, "load_config", lambda: mock_cfg)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    run_oneshot_calls = []
    monkeypatch.setattr(clod, "run_oneshot", lambda *a, **k: run_oneshot_calls.append(True))
    clod.main()
    assert run_oneshot_calls == []


# ── config_path ───────────────────────────────────────────────────────────────


def test_config_path_windows(monkeypatch):
    """On win32, config_path uses APPDATA."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/FakeAppData")
    p = clod.config_path()
    assert "clod" in str(p)
    assert "config.json" in str(p)


def test_config_path_non_windows(monkeypatch):
    """On non-win32, config_path uses ~/.config/clod/config.json."""
    monkeypatch.setattr(sys, "platform", "linux")
    p = clod.config_path()
    assert "config" in str(p)
    assert "clod" in str(p)
    assert p.name == "config.json"


def test_config_path_returns_path_object():
    """config_path() always returns a pathlib.Path."""
    p = clod.config_path()
    assert isinstance(p, pathlib.Path)


# ── history_path ──────────────────────────────────────────────────────────────


def test_history_path():
    """history_path() is a file named 'history' inside the config dir."""
    p = clod.history_path()
    assert p.name == "history"
    assert isinstance(p, pathlib.Path)


def test_history_path_sibling_of_config():
    """history_path() is in the same directory as config_path()."""
    assert clod.history_path().parent == clod.config_path().parent


# ── save_config ───────────────────────────────────────────────────────────────


def test_save_config_writes(tmp_path, monkeypatch):
    """save_config writes JSON to the config path."""
    cfg_file = tmp_path / "clod" / "config.json"
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)
    clod.save_config({"key": "value"})
    data = json.loads(cfg_file.read_text())
    assert data["key"] == "value"


def test_save_config_creates_parent_dirs(tmp_path, monkeypatch):
    """save_config creates intermediate directories if they don't exist."""
    cfg_file = tmp_path / "deep" / "nested" / "config.json"
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)
    clod.save_config({"x": 1})
    assert cfg_file.exists()


def test_save_config_roundtrip(tmp_path, monkeypatch):
    """Config dict survives a save → load roundtrip."""
    cfg_file = tmp_path / "clod" / "config.json"
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)
    original = {"ollama_url": "http://test:1234", "token_budget": 5000}
    clod.save_config(original)
    data = json.loads(cfg_file.read_text())
    assert data["ollama_url"] == "http://test:1234"
    assert data["token_budget"] == 5000


# ── load_config ───────────────────────────────────────────────────────────────


def test_load_config_returns_defaults_when_no_file(tmp_path, monkeypatch):
    """load_config returns defaults when config file does not exist."""
    monkeypatch.setattr(clod, "config_path", lambda: tmp_path / "nonexistent" / "config.json")
    cfg = clod.load_config()
    assert "ollama_url" in cfg
    assert "default_model" in cfg


def test_load_config_invalid_json(tmp_path, monkeypatch):
    """load_config returns defaults even when the JSON file is corrupt."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text("not valid json")
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)
    cfg = clod.load_config()
    assert "ollama_url" in cfg


def test_load_config_merges_user_values(tmp_path, monkeypatch):
    """load_config merges user config over defaults."""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"ollama_url": "http://custom:9999"}))
    monkeypatch.setattr(clod, "config_path", lambda: cfg_file)
    cfg = clod.load_config()
    assert cfg["ollama_url"] == "http://custom:9999"
    # Other defaults should still be present
    assert "default_model" in cfg


def test_load_config_all_default_keys_present(tmp_path, monkeypatch):
    """Default config includes all expected keys."""
    monkeypatch.setattr(clod, "config_path", lambda: tmp_path / "none.json")
    cfg = clod.load_config()
    for key in [
        "ollama_url",
        "litellm_url",
        "litellm_key",
        "pipelines_url",
        "searxng_url",
        "default_model",
        "pipeline",
        "enable_tools",
        "token_budget",
    ]:
        assert key in cfg, f"Missing key: {key}"
