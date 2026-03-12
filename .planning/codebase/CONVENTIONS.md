# Coding Conventions

**Analysis Date:** 2026-03-10

## Naming Patterns

**Files:**
- Module files: lowercase with underscores (e.g., `clod.py`, `mcp_server.py`)
- Test files: `test_*.py` pattern (e.g., `test_startup.py`, `test_model_routing.py`)
- Pipeline files: lowercase with underscores (e.g., `chat_assist_pipe.py`, `code_review_pipe.py`)

**Functions:**
- Public functions: `snake_case` (e.g., `load_config()`, `stream_ollama()`, `pick_adapter()`)
- Private functions (internal use): prefix with single underscore, `snake_case` (e.g., `_parse_dotenv()`, `_check_service_health()`, `_get_clod_root()`)
- Tool executors: `tool_<action>` pattern (e.g., `tool_bash_exec()`, `tool_read_file()`, `tool_write_file()`, `tool_web_search()`)

**Variables:**
- Local variables: `snake_case` (e.g., `model_name`, `total_mb`, `session_state`)
- Dict keys: lowercase with underscores (e.g., `"default_model"`, `"litellm_url"`, `"enable_tools"`)
- Shortened variables in loops: Single letters acceptable (e.g., `f` for fraction in `budget.fraction`)

**Types/Classes:**
- Classes: `PascalCase` (e.g., `TokenBudget`)
- Type annotations: Use modern syntax (e.g., `dict[str, bool]`, `list[str]`, `Optional[dict]`)
- Constants: UPPER_CASE (e.g., `CLOUD_MODEL_PREFIXES`, `TOKEN_LIMIT`, `MCP_SERVER_PORT`)

**Constants Structure:**
- Public constants at module level (e.g., `CLOUD_MODEL_PREFIXES`, `VRAM_TIERS`)
- Private constants with leading underscore (e.g., `_GITHUB_RAW_BASE`, `_CLAUDE_MD_PROMPT`, `_README_PROMPT`)
- Thresholds grouped logically: `TOKEN_WARN = 0.80`, `TOKEN_OFFER = 0.95`, `TOKEN_LIMIT = 1.00`

## Code Style

**Formatting:**
- Tool: Black (enforced via pre-commit hook)
- Line length: 100 characters (configured in `pyproject.toml`)
- Python version: 3.11+ (per `pyproject.toml`)

**Linting:**
- Tool: Pylint
- Fail threshold: 7.0 (score must remain above this)
- Max line length: 100 characters
- Disabled rules: `C0114` (missing module docstrings), `C0115` (missing class docstrings), `C0116` (missing function docstrings), `W0212` (protected-access), `R0903` (too-few-public-methods)
- Security: Bandit configured; intentional exemptions for subprocess (`B404`, `B602`, `B605`)

## Import Organization

**Order:**
1. Standard library imports (stdlib)
2. Third-party imports (external packages like `requests`, `rich`)
3. Local imports (project modules like `clod`)

**Pattern:**
```python
import argparse
import json
import os
import pathlib
import re
import sys

import requests
from prompt_toolkit import PromptSession
from rich.console import Console

import clod
from clod import pick_adapter, TokenBudget
```

**Conditional imports:**
- Optional dependencies wrapped in try/except at module level:
  ```python
  try:
      import psutil as _psutil
      HAS_PSUTIL = True
  except ImportError:
      HAS_PSUTIL = False
  ```

**Path handling:**
- Always use `pathlib.Path` for filesystem operations (not `os.path`)
- Expand user paths with `.expanduser()` for config directories

## Error Handling

**Patterns:**
- Broad exception catching with `except Exception:` when graceful degradation is acceptable
- Specific exception catches for recoverable errors (e.g., `except FileNotFoundError:`, `except requests.ConnectionError:`)
- Service health checks return `False` (not raising) when unreachable
- Tool execution returns error strings (not raising) for display to user

**Example from `clod.py`:**
```python
try:
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
except requests.ConnectionError:
    return False  # service unreachable
except requests.HTTPError as e:
    return False  # service error
except Exception:
    return False  # any other error
```

## Logging

**Framework:** `Rich` console object (global `console` variable)

**Patterns:**
- Status messages: `console.print("[dim]message…[/dim]")`
- Success: `console.print("[green]success[/green]")`
- Warning: `console.print("[yellow]warning[/yellow]")`
- Error: `console.print("[red]error message[/red]")`
- Panels for commands: `console.print(Panel(f"[bold yellow]$ {command}[/bold yellow]", title="[yellow]bash_exec[/yellow]"))`
- Progress bars: `console.print(f"  [cyan][{bar}][/cyan] {pct:3d}%", end="\r")`

**No standard logging module** — all output via Rich console for consistent terminal UI

## Comments

**When to Comment:**
- Section headers: Use decorative line format: `# ── Section Name ─────────────────────────────`
- Complex algorithm explanation: Comment non-obvious logic
- TODOs/FIXMEs: Avoid; use issues instead if possible

**No JSDoc/TSDoc** — Python docstrings used only for module and complex function documentation

**Docstring style (where used):**
```python
def stream_ollama(messages: list, model: str, cfg: dict) -> Generator[dict, None, None]:
    """
    Stream from Ollama /api/chat.
    Yields dicts: {"type": "token", "text": str}
                  {"type": "tool_call", "name": str, "arguments": dict}
                  {"type": "done", "message": dict}
    """
```

## Function Design

**Size:** Functions kept compact, typically 20-80 lines; longer operations split into helpers

**Parameters:**
- Use `dict` for configuration passing (avoids excessive positional args)
- Type hints required for public functions (e.g., `def load_config() -> dict:`)
- Optional parameters use `Optional[]` type hint
- `**kwargs` avoided; explicit parameters preferred

**Return Values:**
- Tuples for multi-value returns: `tuple[bool, str]` (success, message)
- Dicts for structured results: `dict[str, bool]` (service health status)
- Generators for streaming: `Generator[dict, None, None]`
- None for side-effect functions (config writes, prints)

## Module Design

**Exports:**
- All public functions defined at module level
- Private functions use `_` prefix
- No `__all__` list needed; convention sufficient

**Section organization:**
Modules organized with comment sections:
```
# ── Constants ──────────────────────────────────────────────────
# ── Config ─────────────────────────────────────────────────
# ── Tool Executors ─────────────────────────────────────────────
# ── Ollama Model Management ────────────────────────────────────
```

**Files:**
- `clod.py`: Main CLI module (~2,700 lines)
- `mcp_server.py`: MCP filesystem server integration
- `tests/conftest.py`: Shared fixtures (fake_console, mock_cfg, mock_session_state)

**Test imports:**
- Test files add parent directory to `sys.path` for imports:
  ```python
  import sys
  import pathlib
  sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent))
  import clod
  ```

---

*Convention analysis: 2026-03-10*
