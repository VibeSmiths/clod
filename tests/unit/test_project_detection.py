"""
Unit tests for project type detection and context gathering.
"""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import clod
from clod import (
    _detect_project_types,
    _find_project_roots,
    _gather_context,
    MAX_CONTEXT_CHARS_PER_FILE,
    SKIP_DIRS,
)


# ── _detect_project_types ──────────────────────────────────────────────────────


def test_detect_no_signals(tmp_path):
    """An empty directory returns no project types."""
    result = _detect_project_types(tmp_path)
    assert result == []


def test_detect_requirements_txt(tmp_path):
    """A requirements.txt in the directory signals 'Python'."""
    (tmp_path / "requirements.txt").write_text("requests\n")
    result = _detect_project_types(tmp_path)
    assert "Python" in result


def test_detect_dockerfile(tmp_path):
    """A Dockerfile in the directory signals 'Docker'."""
    (tmp_path / "Dockerfile").write_text("FROM python:3.11\n")
    result = _detect_project_types(tmp_path)
    assert "Docker" in result


def test_detect_package_json(tmp_path):
    """A package.json in the directory signals 'Node.js'."""
    (tmp_path / "package.json").write_text('{"name": "test"}\n')
    result = _detect_project_types(tmp_path)
    assert "Node.js" in result


def test_detect_multiple_signals(tmp_path):
    """docker-compose.yml + requirements.txt → multiple types detected."""
    (tmp_path / "docker-compose.yml").write_text("version: '3'\n")
    (tmp_path / "requirements.txt").write_text("requests\n")
    result = _detect_project_types(tmp_path)
    assert "Python" in result
    assert "Docker Compose" in result


def test_detect_glob_pattern(tmp_path):
    """A .csproj file signals '.NET/C#' via glob pattern."""
    (tmp_path / "MyApp.csproj").write_text("<Project />\n")
    result = _detect_project_types(tmp_path)
    assert ".NET/C#" in result


# ── _find_project_roots ────────────────────────────────────────────────────────


def test_find_project_roots_single(tmp_path):
    """A single project sub-directory is discovered."""
    sub = tmp_path / "myproject"
    sub.mkdir()
    (sub / "requirements.txt").write_text("requests\n")

    results = _find_project_roots(tmp_path)
    paths = [p for p, _ in results]
    assert sub in paths


def test_find_project_roots_skips_node_modules(tmp_path):
    """node_modules directories are not returned as project roots."""
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "package.json").write_text('{"name": "dep"}\n')

    results = _find_project_roots(tmp_path)
    paths = [p for p, _ in results]
    assert nm not in paths


# ── _gather_context ────────────────────────────────────────────────────────────


def test_gather_context_contains_path(tmp_path):
    """_gather_context output includes the project path string."""
    (tmp_path / "requirements.txt").write_text("requests\n")
    types = _detect_project_types(tmp_path)
    ctx = _gather_context(tmp_path, types)
    assert str(tmp_path) in ctx


def test_gather_context_reads_key_files(tmp_path):
    """_gather_context includes the content of requirements.txt."""
    (tmp_path / "requirements.txt").write_text("requests==2.31.0\n")
    types = ["Python"]
    ctx = _gather_context(tmp_path, types)
    assert "requests==2.31.0" in ctx


def test_gather_context_truncates_large_files(tmp_path):
    """Files larger than MAX_CONTEXT_CHARS_PER_FILE are truncated."""
    big_content = "x" * (MAX_CONTEXT_CHARS_PER_FILE + 500)
    (tmp_path / "requirements.txt").write_text(big_content)
    types = ["Python"]
    ctx = _gather_context(tmp_path, types)
    assert "...(truncated)" in ctx
    # The full content must NOT be present
    assert big_content not in ctx
