"""
Tests covering remaining coverage gaps:
- ollama_pull (all paths)
- query_system_info (no-psutil path, exception path)
- tool error paths (bash_exec stderr/nonzero/generic-exception, read_file, write_file)
- stream_ollama (tools body, JSON decode error)
- stream_openai_compat (empty lines, non-data lines, JSON decode error)
- _gather_context (hidden items, subdirs, permission errors, file read exception)
- _write_with_status (exception path)
- infer (check_token_thresholds with session_state, 10-round exit)
"""

import sys
import builtins
import platform
import pathlib
import subprocess

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))

import pytest
import requests
import responses as resp_lib

import clod
from clod import TokenBudget

# ── Mock console for tool tests ────────────────────────────────────────────────


class _YesConsole:
    """Console that accepts any confirmation prompt."""

    def print(self, *a, **k):
        pass

    def input(self, *a, **k):
        return "y"

    def status(self, *a, **k):
        import contextlib

        return contextlib.nullcontext()


# ── tool_bash_exec: stderr and nonzero returncode ─────────────────────────────


def test_tool_bash_exec_stderr_captured(monkeypatch):
    """Command with stderr output includes 'stderr:' in result."""
    console = _YesConsole()

    def fake_run(*a, **k):
        return subprocess.CompletedProcess(args=a, returncode=0, stdout="", stderr="some warning")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = clod.tool_bash_exec({"command": "cmd"}, console)
    assert "stderr" in result
    assert "some warning" in result


def test_tool_bash_exec_nonzero_returncode(monkeypatch):
    """Command with nonzero returncode includes 'returncode:' in result."""
    console = _YesConsole()

    def fake_run(*a, **k):
        return subprocess.CompletedProcess(args=a, returncode=2, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = clod.tool_bash_exec({"command": "cmd"}, console)
    assert "returncode: 2" in result


def test_tool_bash_exec_generic_exception(monkeypatch):
    """Generic exception from subprocess.run returns 'Error: ...' string."""
    console = _YesConsole()

    def raise_err(*a, **k):
        raise MemoryError("out of memory")

    monkeypatch.setattr(subprocess, "run", raise_err)
    result = clod.tool_bash_exec({"command": "cmd"}, console)
    assert "Error:" in result


# ── tool_read_file: non-FileNotFoundError exception ───────────────────────────


def test_tool_read_file_permission_error(monkeypatch, tmp_path):
    """PermissionError on open → returns 'Error reading file: ...'."""
    f = tmp_path / "secret.txt"
    f.write_text("private")

    original_open = builtins.open

    def mock_open(file, *a, **k):
        if str(file) == str(f):
            raise PermissionError("permission denied")
        return original_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", mock_open)
    result = clod.tool_read_file({"path": str(f)})
    assert "Error reading file" in result


# ── tool_write_file: exception ────────────────────────────────────────────────


def test_tool_write_file_io_error(monkeypatch, tmp_path):
    """IOError on open → returns 'Error writing file: ...'."""
    f = tmp_path / "out.txt"

    original_open = builtins.open

    def mock_open(file, *a, **k):
        if str(file) == str(f):
            raise IOError("disk full")
        return original_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", mock_open)
    result = clod.tool_write_file({"path": str(f), "content": "data"})
    assert "Error writing file" in result


# ── ollama_pull ────────────────────────────────────────────────────────────────


@resp_lib.activate
def test_ollama_pull_connection_error(fake_console):
    """ConnectionError prints error and returns early."""
    resp_lib.add(
        resp_lib.POST,
        "http://localhost:11434/api/pull",
        body=requests.exceptions.ConnectionError(),
    )
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    clod.ollama_pull("test-model", "http://localhost:11434")
    assert any("Cannot connect" in s for s in printed)


@resp_lib.activate
def test_ollama_pull_http_error(fake_console):
    """HTTP 404 prints pull error and returns early."""
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/pull", status=404, body=b"Not Found")
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    clod.ollama_pull("test-model", "http://localhost:11434")
    assert any("error" in s.lower() for s in printed)


@resp_lib.activate
def test_ollama_pull_success_with_progress(fake_console):
    """Progress events with total/completed are displayed as a progress bar."""
    body = (
        b'{"status": "downloading", "total": 1000, "completed": 500}\n'
        b'{"status": "downloading", "total": 1000, "completed": 1000}\n'
        b'{"status": "success"}\n'
    )
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/pull", body=body)
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    clod.ollama_pull("test-model", "http://localhost:11434")
    assert any("done" in s.lower() or "ready" in s.lower() for s in printed)


@resp_lib.activate
def test_ollama_pull_success_status_only(fake_console):
    """Events with only status (no total/completed) use the simple display."""
    body = b'{"status": "verifying sha256 digest"}\n' b'{"status": "success"}\n'
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/pull", body=body)
    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))
    clod.ollama_pull("test-model", "http://localhost:11434")
    assert any("done" in s.lower() or "ready" in s.lower() for s in printed)


@resp_lib.activate
def test_ollama_pull_skips_invalid_json(fake_console):
    """Invalid JSON lines in the stream are silently skipped."""
    body = b"not-valid-json\n" + b'{"status": "done"}\n'
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/pull", body=body)
    # Should not raise
    clod.ollama_pull("test-model", "http://localhost:11434")


@resp_lib.activate
def test_ollama_pull_skips_empty_lines(fake_console):
    """Empty lines in the pull response are silently skipped."""
    body = b"\n" + b'{"status": "done"}\n' + b"\n"
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/pull", body=body)
    clod.ollama_pull("test-model", "http://localhost:11434")


# ── query_system_info: no-psutil and exception paths ─────────────────────────


def test_query_system_info_no_psutil(monkeypatch):
    """When HAS_PSUTIL is False, RAM values are 0."""
    monkeypatch.setattr(clod, "HAS_PSUTIL", False)
    result = clod.query_system_info()
    assert isinstance(result, dict)
    assert result.get("ram_total_mb") == 0
    assert result.get("ram_available_mb") == 0


def test_query_system_info_exception(monkeypatch):
    """If platform.processor() raises, query_system_info returns {}."""
    import platform as _platform

    def raise_err():
        raise RuntimeError("platform error")

    monkeypatch.setattr(_platform, "processor", raise_err)
    result = clod.query_system_info()
    assert result == {}


# ── stream_ollama: tools body and JSON decode error ───────────────────────────


@resp_lib.activate
def test_stream_ollama_with_tools_sends_tools(mock_cfg):
    """When tools param is non-empty, body["tools"] is set (line 887)."""
    body = b'{"message": {"content": "result"}, "done": true}\n'
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/chat", body=body)

    tools = [{"type": "function", "function": {"name": "bash_exec"}}]
    events = list(clod.stream_ollama([], "model", mock_cfg, tools=tools))
    tokens = [e for e in events if e["type"] == "token"]
    assert any(e["text"] == "result" for e in tokens)


@resp_lib.activate
def test_stream_ollama_skips_invalid_json_lines(mock_cfg):
    """Invalid JSON lines in the NDJSON body are skipped (lines 912-913)."""
    body = b"not-valid-json\n" + b'{"message": {"content": "ok"}, "done": true}\n'
    resp_lib.add(resp_lib.POST, "http://localhost:11434/api/chat", body=body)

    events = list(clod.stream_ollama([], "model", mock_cfg))
    tokens = [e for e in events if e["type"] == "token"]
    assert any(e["text"] == "ok" for e in tokens)


# ── stream_openai_compat: skip branches and JSON decode error ─────────────────


@resp_lib.activate
def test_stream_openai_compat_skips_empty_lines(mock_cfg):
    """Empty lines in SSE stream are silently skipped (line 975)."""
    body = b"\n" b'data: {"choices": [{"delta": {"content": "hi"}}]}\n' b"\n" b"data: [DONE]\n"
    resp_lib.add(resp_lib.POST, "http://localhost:4000/v1/chat/completions", body=body)

    events = list(clod.stream_openai_compat([], "model", "http://localhost:4000", "key"))
    tokens = [e for e in events if e["type"] == "token"]
    assert any(e["text"] == "hi" for e in tokens)


@resp_lib.activate
def test_stream_openai_compat_skips_non_data_lines(mock_cfg):
    """Lines not starting with 'data: ' are skipped (line 978)."""
    body = (
        b"event: ping\n"
        b": comment\n"
        b'data: {"choices": [{"delta": {"content": "hello"}}]}\n'
        b"data: [DONE]\n"
    )
    resp_lib.add(resp_lib.POST, "http://localhost:4000/v1/chat/completions", body=body)

    events = list(clod.stream_openai_compat([], "model", "http://localhost:4000", "key"))
    tokens = [e for e in events if e["type"] == "token"]
    assert any(e["text"] == "hello" for e in tokens)


@resp_lib.activate
def test_stream_openai_compat_skips_invalid_json(mock_cfg):
    """Invalid JSON after 'data: ' is skipped (lines 988-989)."""
    body = (
        b"data: not-valid-json\n"
        b'data: {"choices": [{"delta": {"content": "world"}}]}\n'
        b"data: [DONE]\n"
    )
    resp_lib.add(resp_lib.POST, "http://localhost:4000/v1/chat/completions", body=body)

    events = list(clod.stream_openai_compat([], "model", "http://localhost:4000", "key"))
    tokens = [e for e in events if e["type"] == "token"]
    assert any(e["text"] == "world" for e in tokens)


# ── _gather_context ────────────────────────────────────────────────────────────


def test_gather_context_skips_hidden_and_skip_dirs(tmp_path):
    """Items starting with '.' or in SKIP_DIRS are skipped (line 1073 continue)."""
    (tmp_path / ".hidden").write_text("hidden content")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "visible.py").write_text("def foo(): pass")

    result = clod._gather_context(tmp_path, ["python"])
    assert "visible.py" in result
    assert ".hidden" not in result


def test_gather_context_includes_subdirectory_files(tmp_path):
    """Subdirectory contents are listed (lines 1075-1079)."""
    sub = tmp_path / "mylib"
    sub.mkdir()
    (sub / "utils.py").write_text("def helper(): pass")

    result = clod._gather_context(tmp_path, ["python"])
    assert "mylib" in result
    assert "utils.py" in result


def test_gather_context_subdirectory_permission_error(monkeypatch, tmp_path):
    """PermissionError on subdirectory iteration is caught silently (lines 1080-1081)."""
    sub = tmp_path / "protected"
    sub.mkdir()

    original_iterdir = pathlib.Path.iterdir
    call_count = [0]

    def mock_iterdir(self):
        call_count[0] += 1
        # Second call is the subdirectory — make it raise
        if call_count[0] >= 2:
            raise PermissionError("access denied")
        return original_iterdir(self)

    monkeypatch.setattr(pathlib.Path, "iterdir", mock_iterdir)
    result = clod._gather_context(tmp_path, ["python"])
    assert "Project path" in result  # function completes normally


def test_gather_context_top_level_permission_error(monkeypatch, tmp_path):
    """PermissionError at the top level is caught silently (lines 1082-1083)."""

    def raise_perm(self):
        raise PermissionError("cannot list dir")

    monkeypatch.setattr(pathlib.Path, "iterdir", raise_perm)
    result = clod._gather_context(tmp_path, ["python"])
    assert "Project path" in result  # function completes normally


def test_gather_context_file_read_exception(monkeypatch, tmp_path):
    """Exception reading a context file is caught silently (line 1102)."""
    readme = tmp_path / "README.md"
    readme.write_text("# Test project")

    original_read_text = pathlib.Path.read_text

    def mock_read_text(self, *args, **kwargs):
        if self.name == "README.md":
            raise PermissionError("cannot read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", mock_read_text)
    result = clod._gather_context(tmp_path, ["python"])
    assert "Project path" in result  # function completes normally


# ── _write_with_status ────────────────────────────────────────────────────────


def test_write_with_status_exception(monkeypatch, fake_console, tmp_path):
    """write_text failure prints error message (lines 1146-1147)."""
    f = tmp_path / "output.md"

    printed = []
    fake_console.print = lambda *a, **k: printed.append(str(a))

    def raise_write(self, *args, **kwargs):
        raise IOError("disk full")

    monkeypatch.setattr(pathlib.Path, "write_text", raise_write)
    clod._write_with_status(f, "content", "output.md")
    assert any("error" in s.lower() for s in printed)


# ── infer: check_token_thresholds with session_state (line 1423) ──────────────


def test_infer_check_token_thresholds_called(monkeypatch, fake_console, mock_cfg):
    """check_token_thresholds is called when uses_claude and session_state are set."""
    monkeypatch.setattr(clod, "stream_and_render", lambda gen: ("claude answer", []))
    thresholds_called = []
    monkeypatch.setattr(clod, "check_token_thresholds", lambda b, s: thresholds_called.append(True))

    budget = TokenBudget(100_000)
    session_state = {
        "model": "claude-sonnet-4-6",
        "offline": False,
        "cfg": mock_cfg,
        "budget": budget,
    }

    clod.infer(
        [{"role": "user", "content": "hi"}],
        "claude-sonnet-4-6",
        None,
        mock_cfg,
        False,
        budget=budget,
        session_state=session_state,
    )
    assert thresholds_called


# ── infer: 10-round max tool call exit (line 1444) ────────────────────────────


def test_infer_max_tool_rounds_returns_last_content(monkeypatch, fake_console, mock_cfg):
    """After 10 tool-call rounds, infer exits the loop and returns final_content."""
    monkeypatch.setattr(clod, "ensure_ollama_model", lambda m, c: True)

    tool_call = {"type": "tool_call", "name": "bash_exec", "arguments": {"command": "ls"}}
    call_count = [0]

    def fake_stream_and_render(gen):
        call_count[0] += 1
        # Always return a tool_call — forces 10 iterations
        return ("partial content", [tool_call])

    monkeypatch.setattr(clod, "stream_and_render", fake_stream_and_render)
    monkeypatch.setattr(
        clod, "execute_tool", lambda name, args, console, cfg, features=None: "result"
    )

    result = clod.infer(
        [{"role": "user", "content": "run"}],
        "qwen2.5-coder:14b",
        None,
        mock_cfg,
        True,
    )
    # Loop ran exactly 10 times
    assert call_count[0] == 10
    # Returns final_content or "" from the last round
    assert result == "partial content"
