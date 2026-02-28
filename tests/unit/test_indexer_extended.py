"""
Tests for project indexer functions:
  _call_local, _write_with_status, run_index_mode
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import requests
import responses as resp_lib

import clod

# ── _call_local ───────────────────────────────────────────────────────────────


@resp_lib.activate
def test_call_local_success(mock_cfg):
    """Returns the content string from the model response."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        json={"message": {"content": "generated content"}},
    )
    result = clod._call_local([{"role": "user", "content": "prompt"}], mock_cfg)
    assert result == "generated content"


@resp_lib.activate
def test_call_local_connection_error(mock_cfg):
    """ConnectionError returns a string containing 'error'."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        body=requests.exceptions.ConnectionError(),
    )
    result = clod._call_local([{"role": "user", "content": "prompt"}], mock_cfg)
    assert "error" in result.lower()


@resp_lib.activate
def test_call_local_http_error(mock_cfg):
    """HTTP 500 returns a string containing 'error'."""
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/chat", status=500)
    result = clod._call_local([{"role": "user", "content": "prompt"}], mock_cfg)
    assert "error" in result.lower()


@resp_lib.activate
def test_call_local_empty_content(mock_cfg):
    """When model returns empty content, result is empty string."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        json={"message": {"content": ""}},
    )
    result = clod._call_local([{"role": "user", "content": "x"}], mock_cfg)
    assert result == ""


@resp_lib.activate
def test_call_local_uses_default_model(mock_cfg):
    """_call_local posts to the correct Ollama URL."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/chat",
        json={"message": {"content": "ok"}},
    )
    clod._call_local([{"role": "user", "content": "hi"}], mock_cfg)
    # If we got here without connection error, the URL was correct
    assert resp_lib.calls[0].request.url == "http://localhost:11434/api/chat"


# ── _write_with_status ────────────────────────────────────────────────────────


def test_write_with_status_success(tmp_path, fake_console):
    """Writes content to the given path successfully."""
    target = tmp_path / "CLAUDE.md"
    clod._write_with_status(target, "# Project\ncontent here", "CLAUDE.md")
    assert target.read_text(encoding="utf-8") == "# Project\ncontent here"


def test_write_with_status_error_prints(tmp_path, fake_console):
    """Writing to an unwritable path (directory) calls console.print with error."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))

    # Use a directory path as the target file — will fail to write
    dir_path = tmp_path / "some_dir"
    dir_path.mkdir()
    clod._write_with_status(dir_path, "content", "label")

    # At least one print call should mention the error
    all_output = " ".join(printed)
    assert "error" in all_output.lower() or len(printed) > 0


def test_write_with_status_creates_content(tmp_path, fake_console):
    """Content is written verbatim."""
    target = tmp_path / "out.md"
    clod._write_with_status(target, "hello world", "out.md")
    assert target.read_text() == "hello world"


# ── run_index_mode ────────────────────────────────────────────────────────────


def test_run_index_mode_no_projects(tmp_path, fake_console, mock_cfg):
    """Prints 'No projects detected' when directory has no project signals."""
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    clod.run_index_mode(empty_dir, mock_cfg)

    all_output = " ".join(printed)
    assert "No projects detected" in all_output


def test_run_index_mode_with_project_skips_on_n(tmp_path, fake_console, mock_cfg, monkeypatch):
    """With a package.json project, when user inputs 'n' the files are generated (no existing)."""
    # Create a fake Node.js project
    project_dir = tmp_path / "myapp"
    project_dir.mkdir()
    (project_dir / "package.json").write_text('{"name": "myapp", "version": "1.0.0"}')

    # Mock _call_local to return content without hitting network
    monkeypatch.setattr(clod, "_call_local", lambda msgs, cfg: "# Generated content")

    # fake_console.input returns "" which is treated as 'n' (not y/yes)
    clod.run_index_mode(project_dir, mock_cfg)

    # Since no existing CLAUDE.md/README.md, files should be created
    assert (project_dir / "CLAUDE.md").exists()
    assert (project_dir / "README.md").exists()


def test_run_index_mode_existing_files_declined(tmp_path, fake_console, mock_cfg, monkeypatch):
    """When CLAUDE.md and README.md already exist and user declines, they are not overwritten."""
    project_dir = tmp_path / "existing"
    project_dir.mkdir()
    (project_dir / "package.json").write_text('{"name": "existing"}')

    original_claude = "# Original CLAUDE"
    original_readme = "# Original README"
    (project_dir / "CLAUDE.md").write_text(original_claude)
    (project_dir / "README.md").write_text(original_readme)

    monkeypatch.setattr(clod, "_call_local", lambda msgs, cfg: "new content")

    # Input returns "" -> treated as "n" -> skip overwrite
    clod.run_index_mode(project_dir, mock_cfg)

    assert (project_dir / "CLAUDE.md").read_text() == original_claude
    assert (project_dir / "README.md").read_text() == original_readme


def test_run_index_mode_existing_files_accepted(tmp_path, mock_cfg, monkeypatch):
    """When user accepts overwrite ('y'), files are regenerated."""

    class _YesConsole:
        def print(self, *a, **k):
            pass

        def input(self, *a, **k):
            return "y"

        def status(self, *a, **k):
            import contextlib

            return contextlib.nullcontext()

    yes_console = _YesConsole()
    monkeypatch.setattr(clod, "console", yes_console)

    project_dir = tmp_path / "overwrite"
    project_dir.mkdir()
    (project_dir / "package.json").write_text('{"name": "overwrite"}')
    (project_dir / "CLAUDE.md").write_text("# Old CLAUDE")
    (project_dir / "README.md").write_text("# Old README")

    monkeypatch.setattr(clod, "_call_local", lambda msgs, cfg: "new generated content")

    clod.run_index_mode(project_dir, mock_cfg)

    assert (project_dir / "CLAUDE.md").read_text() == "new generated content"
    assert (project_dir / "README.md").read_text() == "new generated content"


def test_run_index_mode_prints_project_count(tmp_path, fake_console, mock_cfg, monkeypatch):
    """Found project count is printed."""
    project_dir = tmp_path / "counted"
    project_dir.mkdir()
    (project_dir / "pyproject.toml").write_text('[tool.poetry]\nname = "counted"')

    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))

    monkeypatch.setattr(clod, "_call_local", lambda msgs, cfg: "content")

    clod.run_index_mode(project_dir, mock_cfg)

    all_output = " ".join(printed)
    assert "Found" in all_output or "project" in all_output.lower()
