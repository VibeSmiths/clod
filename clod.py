#!/usr/bin/env python3
"""
clod — Local Claude CLI using Ollama + OpenWebUI Pipelines

Mimics the Claude CLI UX but runs entirely against the local stack:
  • Ollama         for local LLM inference (direct streaming)
  • LiteLLM        for cloud models (claude-sonnet, gpt-4o, etc.)
  • Pipelines      for two-stage local→Claude review flows

Usage:
  clod                           interactive REPL
  clod -p "prompt"               one-shot mode
  clod --model deepseek-r1:14b   model override
  clod --pipeline code_review    use a two-stage pipeline
  clod --tools                   enable tool use (bash, file, web search)
  echo "prompt" | clod           pipe mode (one-shot)
"""

import argparse
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import urllib.parse
from typing import Generator, Optional

import requests

try:
    import psutil as _psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

__version__ = "1.0.0"

# ── Constants ──────────────────────────────────────────────────────────────────

CLOUD_MODEL_PREFIXES = ("claude-", "gpt-", "o1-", "o3-", "gemini-", "groq-", "together-")

SD_WEBUI_URL = "http://localhost:7860"  # AUTOMATIC1111 WebUI (stable-diffusion container)
COMFYUI_URL = "http://localhost:8188"   # ComfyUI video service

SONNET_MODEL = "claude-sonnet-4-6"

# Per-pipeline model assignments — local (Ollama) + Claude (LiteLLM alias).
# These mirror the Valves defaults in each pipeline .py file and are used here
# for display, warmup, and token-budget routing.
PIPELINE_CONFIGS: dict[str, dict] = {
    "code_review": {
        "local": "qwen2.5-coder:32b-instruct-q4_K_M",
        "claude": "claude-sonnet",
        "description": "Code gen → senior-engineer review",
    },
    "reason_review": {
        "local": "deepseek-r1:14b",
        "claude": "claude-sonnet",
        "description": "Chain-of-thought → architect structuring",
    },
    "chat_assist": {
        "local": "llama3.1:8b",
        "claude": "claude-haiku",
        "description": "Conversational draft → light polish",
    },
}

# Token-budget thresholds (fraction of session budget)
TOKEN_WARN = 0.80  # yellow warning
TOKEN_OFFER = 0.95  # prompt to go offline
TOKEN_LIMIT = 1.00  # force offline

# VRAM tier table — (min_effective_mb, model_name, label)
# effective = total VRAM - 2000 MiB reserved for CUDA driver overhead
VRAM_TIERS: list[tuple[int, str, str]] = [
    (22_000, "qwen2.5-coder:32b-instruct-q4_K_M", "32b coder  (~20 GB)"),
    (11_000, "qwen2.5-coder:14b",                  "14b coder  (~10 GB)"),
    (9_500,  "deepseek-r1:14b",                    "14b reason (~9 GB) "),
    (5_000,  "llama3.1:8b",                        "8b chat    (~5 GB) "),
]
VRAM_CUDA_OVERHEAD_MB = 2_000  # headroom reserved from total for CUDA runtime

# Project type detection: (glob_pattern, label).
# Patterns starting with "*" are passed to Path.glob(); others are exact names.
PROJECT_SIGNALS: list[tuple[str, str]] = [
    ("*.csproj", ".NET/C#"),
    ("*.sln", ".NET Solution"),
    ("package.json", "Node.js"),
    ("pyproject.toml", "Python"),
    ("setup.py", "Python"),
    ("requirements.txt", "Python"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("pom.xml", "Java/Maven"),
    ("build.gradle", "Java/Gradle"),
    ("build.gradle.kts", "Java/Gradle"),
    ("CMakeLists.txt", "C/C++"),
    ("Makefile", "Make"),
    ("Dockerfile", "Docker"),
    ("docker-compose.yml", "Docker Compose"),
    ("*.tf", "Terraform"),
    (".git", "Git repo"),
]

SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "env",
        "bin",
        "obj",
        "dist",
        "build",
        "target",
        ".next",
        ".nuxt",
        "vendor",
        ".gradle",
        ".idea",
        ".vs",
        "packages",
        ".mypy_cache",
        ".pytest_cache",
        "coverage",
    }
)

# Files whose contents are worth reading for project context
CONTEXT_FILE_PATTERNS = [
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "docker-compose.yml",
    "Dockerfile",
    "README.md",
    "*.csproj",
    "*.sln",
]
MAX_CONTEXT_CHARS_PER_FILE = 2000

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "bash_exec",
            "description": (
                "Execute a shell command and return its stdout and stderr. "
                "Use for running scripts, checking system state, or any terminal operation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 30)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from disk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative file path"},
                    "lines": {"type": "integer", "description": "Max lines to read (0 = all)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or append content to a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write to"},
                    "content": {"type": "string", "description": "Content to write"},
                    "append": {
                        "type": "boolean",
                        "description": "Append instead of overwrite (default false)",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using the local SearXNG instance and return results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "count": {
                        "type": "integer",
                        "description": "Number of results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
]

# ── Config ─────────────────────────────────────────────────────────────────────


def config_path() -> pathlib.Path:
    if sys.platform == "win32":
        base = pathlib.Path(os.environ.get("APPDATA", "~")).expanduser()
    else:
        base = pathlib.Path("~/.config").expanduser()
    return base / "clod" / "config.json"


def history_path() -> pathlib.Path:
    return config_path().parent / "history"


def load_config() -> dict:
    defaults = {
        "ollama_url": "http://localhost:11434",
        "litellm_url": "http://localhost:4000",
        "litellm_key": "sk-local-dev",
        "pipelines_url": "http://localhost:9099",
        "searxng_url": "http://localhost:8080",
        "default_model": "qwen2.5-coder:14b",
        "pipeline": None,
        "enable_tools": False,
        "token_budget": 100_000,  # session Claude token budget (input + output)
        "auto_model": False,
        "compose_file": str(pathlib.Path(__file__).parent / "docker-compose.yml"),
        "dotenv_file":  str(pathlib.Path(__file__).parent / ".env"),
        "sd_mode":      "image",   # last-active SD mode: "image" | "video"
    }
    path = config_path()
    if path.exists():
        try:
            with open(path) as f:
                user = json.load(f)
            defaults.update(user)
        except Exception:
            pass
    return defaults


def save_config(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Tool Executors ─────────────────────────────────────────────────────────────


def tool_bash_exec(args: dict, console: Console) -> str:
    command = args.get("command", "")
    timeout = int(args.get("timeout", 30))
    console.print(
        Panel(
            f"[bold yellow]$ {command}[/bold yellow]",
            title="[yellow]bash_exec[/yellow]",
            border_style="yellow",
        )
    )
    confirmed = console.input("[yellow]Run this command? [y/N] [/yellow]").strip().lower()
    if confirmed not in ("y", "yes"):
        return "User declined to execute this command."
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = ""
        if result.stdout:
            output += f"stdout:\n{result.stdout}"
        if result.stderr:
            output += f"\nstderr:\n{result.stderr}"
        if result.returncode != 0:
            output += f"\nreturncode: {result.returncode}"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def tool_read_file(args: dict) -> str:
    path = pathlib.Path(args.get("path", "")).expanduser()
    max_lines = int(args.get("lines", 0))
    try:
        with open(path) as f:
            if max_lines > 0:
                lines = [f.readline() for _ in range(max_lines)]
                content = "".join(lines)
            else:
                content = f.read()
        return content if content else "(empty file)"
    except FileNotFoundError:
        return f"File not found: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


def tool_write_file(args: dict) -> str:
    path = pathlib.Path(args.get("path", "")).expanduser()
    content = args.get("content", "")
    append = bool(args.get("append", False))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(path, mode) as f:
            f.write(content)
        action = "Appended to" if append else "Wrote"
        return f"{action} {path} ({len(content)} chars)"
    except Exception as e:
        return f"Error writing file: {e}"


def tool_web_search(args: dict, searxng_url: str) -> str:
    query = args.get("query", "")
    count = int(args.get("count", 5))
    try:
        params = {"q": query, "format": "json", "language": "en"}
        resp = requests.get(
            f"{searxng_url}/search",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])[:count]
        if not results:
            return "No results found."
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r.get('title', 'No title')}")
            lines.append(f"   {r.get('url', '')}")
            if r.get("content"):
                snippet = r["content"][:200].replace("\n", " ")
                lines.append(f"   {snippet}")
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


def execute_tool(name: str, args: dict, console: Console, cfg: dict) -> str:
    if name == "bash_exec":
        return tool_bash_exec(args, console)
    elif name == "read_file":
        return tool_read_file(args)
    elif name == "write_file":
        return tool_write_file(args)
    elif name == "web_search":
        return tool_web_search(args, cfg["searxng_url"])
    else:
        return f"Unknown tool: {name}"


# ── Ollama Model Management ────────────────────────────────────────────────────


def ollama_local_models(ollama_url: str) -> list[str]:
    """Return list of model names currently available in Ollama."""
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
        resp.raise_for_status()
        return [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return []


def ollama_model_available(model: str, ollama_url: str) -> bool:
    """Check if a model (or a tag-normalised match) exists locally."""
    available = ollama_local_models(ollama_url)
    # Normalise: "qwen2.5-coder:14b" matches "qwen2.5-coder:14b"
    # Also match bare name against "name:latest"
    candidates = {m for m in available} | {m.split(":")[0] for m in available}
    return model in candidates or f"{model}:latest" in available


def ollama_pull(model: str, ollama_url: str) -> None:
    """
    Pull a model via the Ollama API with a Rich progress display.
    Streams NDJSON progress events until complete.
    """
    console.print(f"[dim]Pulling [bold]{model}[/bold] from Ollama registry…[/dim]")
    try:
        resp = requests.post(
            f"{ollama_url}/api/pull",
            json={"name": model, "stream": True},
            stream=True,
            timeout=3600,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        console.print(f"[red]Cannot connect to Ollama at {ollama_url}[/red]")
        return
    except requests.HTTPError as e:
        console.print(f"[red]Ollama pull error: {e}[/red]")
        return

    last_status = ""
    for raw in resp.iter_lines():
        if not raw:
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue

        status = event.get("status", "")
        total = event.get("total", 0)
        completed = event.get("completed", 0)

        if status != last_status:
            last_status = status
            if total and completed:
                pct = int(completed / total * 100)
                bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
                console.print(f"  [cyan][{bar}][/cyan] {pct:3d}%  {status}", end="\r")
            else:
                console.print(f"  [dim]{status}[/dim]")

    console.print(f"\n[green]done[/green] [bold]{model}[/bold] ready")


def ensure_ollama_model(model: str, cfg: dict) -> bool:
    """
    Ensure the given Ollama model is available locally, pulling if needed.
    Returns True if the model is ready, False if it could not be obtained.
    """
    ollama_url = cfg["ollama_url"]
    if ollama_model_available(model, ollama_url):
        return True
    console.print(f"[yellow]Model [bold]{model}[/bold] not found locally.[/yellow]")
    ollama_pull(model, ollama_url)
    return ollama_model_available(model, ollama_url)


def warmup_ollama_model(model: str, cfg: dict) -> None:
    """
    Send a minimal request to Ollama so the model is loaded into VRAM before
    the user's first real prompt. Shows a spinner while waiting.
    Skips silently on any connection error (non-fatal).
    """
    with console.status(
        f"[dim]Loading [bold]{model}[/bold] into memory…[/dim]",
        spinner="dots",
    ):
        try:
            requests.post(
                f"{cfg['ollama_url']}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "stream": False,
                    "options": {"num_predict": 1, "num_ctx": 512},
                },
                timeout=120,
            )
        except Exception:
            pass  # warmup failure is non-fatal


def query_gpu_vram() -> Optional[dict]:
    """
    Query nvidia-smi for GPU info. Returns dict with keys:
      name, total_mb, free_mb
    Returns None if nvidia-smi is unavailable (no GPU / not NVIDIA).
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().splitlines()[0]
        name, total, free = [x.strip() for x in line.split(",")]
        return {"name": name, "total_mb": int(total), "free_mb": int(free)}
    except Exception:
        return None


def recommend_model_for_vram(total_mb: int) -> Optional[str]:
    """Return the best-fitting model name for the given total VRAM, or None."""
    effective = total_mb - VRAM_CUDA_OVERHEAD_MB
    for min_mb, model, _ in VRAM_TIERS:
        if effective >= min_mb:
            return model
    return None


def query_system_info() -> dict:
    """
    Return CPU and RAM info.
    Keys: cpu_name, cpu_physical, cpu_logical, ram_total_mb, ram_available_mb.
    Gracefully returns partial dict if psutil is unavailable.
    """
    try:
        cpu_name = platform.processor() or platform.machine() or "unknown"
        logical = os.cpu_count() or 0
        if HAS_PSUTIL:
            physical = _psutil.cpu_count(logical=False) or logical
            vm = _psutil.virtual_memory()
            ram_total_mb = vm.total // (1024 * 1024)
            ram_available_mb = vm.available // (1024 * 1024)
        else:
            physical = logical
            ram_total_mb = 0
            ram_available_mb = 0
        return {
            "cpu_name": cpu_name,
            "cpu_physical": physical,
            "cpu_logical": logical,
            "ram_total_mb": ram_total_mb,
            "ram_available_mb": ram_available_mb,
        }
    except Exception:
        return {}


def query_comfyui_running() -> bool:
    """Return True if the Stable Diffusion WebUI (AUTOMATIC1111) is reachable on localhost:7860."""
    try:
        r = requests.get(SD_WEBUI_URL, timeout=2)
        return r.status_code < 500
    except Exception:
        return False


def find_comfyui_container() -> Optional[str]:
    """
    Return the Docker container name bound to port 7860 (the stable-diffusion service),
    including stopped containers, or None if not found.
    """
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--filter", "publish=7860", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            names = r.stdout.strip().splitlines()
            return names[0] if names else None
    except Exception:
        pass
    return None


def comfyui_docker_action(action: str) -> tuple[bool, str]:
    """
    Stop or start the ComfyUI Docker container.
    action: 'stop' | 'start'
    Returns (success: bool, message: str).
    """
    container = find_comfyui_container()
    if not container:
        return False, "Stable Diffusion container not found via 'docker ps -a --filter publish=7860'"
    try:
        r = subprocess.run(
            ["docker", action, container],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            return True, f"docker {action} {container}: OK"
        return False, (r.stderr.strip() or f"exit code {r.returncode}")
    except FileNotFoundError:
        return False, "docker CLI not found — is Docker Desktop running?"
    except Exception as e:
        return False, str(e)


def query_video_running() -> bool:
    """Return True if ComfyUI (video) is reachable on localhost:8188."""
    try:
        r = requests.get(COMFYUI_URL, timeout=2)
        return r.status_code < 500
    except Exception:
        return False


def update_dotenv_key(dotenv_path: str, key: str, value: str) -> bool:
    """Update (or append) KEY=value in a .env file. Returns False on any error."""
    try:
        path = pathlib.Path(dotenv_path)
        if not path.exists():
            return False
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        updated = False
        for i, line in enumerate(lines):
            if re.match(rf"^{re.escape(key)}\s*=", line):
                lines[i] = f"{key}={value}\n"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}\n")
        path.write_text("".join(lines), encoding="utf-8")
        return True
    except Exception:
        return False


def sd_switch_mode(to_mode: str, cfg: dict) -> tuple[bool, str]:
    """
    Switch the active SD mode ('image' | 'video') by:
      1. Updating IMAGE_GENERATION_ENGINE in .env
      2. Stopping the old profile's services
      3. Starting the new profile's services
      4. Force-recreating open-webui to pick up the engine change
    Returns (success, message).
    """
    if to_mode not in ("image", "video"):
        return False, f"Unknown mode '{to_mode}' — use 'image' or 'video'"
    from_mode = "video" if to_mode == "image" else "image"
    compose   = cfg.get("compose_file", "")
    dotenv    = cfg.get("dotenv_file",  "")
    engine    = "automatic1111" if to_mode == "image" else "comfyui"

    if not pathlib.Path(compose).exists():
        return False, f"docker-compose.yml not found at {compose}"

    errors: list[str] = []

    # 1. Update .env
    if dotenv and not update_dotenv_key(dotenv, "IMAGE_GENERATION_ENGINE", engine):
        errors.append("could not update .env (non-fatal)")

    base_cmd = ["docker", "compose", "-f", compose]

    # 2. Stop old profile
    try:
        r = subprocess.run(
            base_cmd + ["--profile", from_mode, "stop"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            errors.append(f"stop {from_mode}: {r.stderr.strip()}")
    except Exception as e:
        errors.append(f"stop {from_mode}: {e}")

    # 3. Start new profile
    try:
        r = subprocess.run(
            base_cmd + ["--profile", to_mode, "up", "-d"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            errors.append(f"up {to_mode}: {r.stderr.strip()}")
    except Exception as e:
        errors.append(f"up {to_mode}: {e}")

    # 4. Restart open-webui to adopt new IMAGE_GENERATION_ENGINE
    try:
        r = subprocess.run(
            base_cmd + ["up", "-d", "--force-recreate", "open-webui"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            errors.append(f"restart open-webui: {r.stderr.strip()}")
    except Exception as e:
        errors.append(f"restart open-webui: {e}")

    if errors:
        return False, " | ".join(errors)
    return True, f"Switched to {to_mode} mode (engine={engine})"


def comfyui_docker_action_video(action: str) -> tuple[bool, str]:
    """Stop/start the ComfyUI (video) container via port 8188."""
    try:
        r = subprocess.run(
            ["docker", "ps", "-a", "--filter", "publish=8188", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5,
        )
        container = r.stdout.strip().splitlines()[0] if r.returncode == 0 else None
    except Exception:
        container = None
    if not container:
        return False, "ComfyUI (video) container not found"
    try:
        r = subprocess.run(["docker", action, container], capture_output=True, text=True, timeout=30)
        return (r.returncode == 0), (r.stderr.strip() or f"docker {action} {container}: OK")
    except FileNotFoundError:
        return False, "docker CLI not found"
    except Exception as e:
        return False, str(e)


def print_startup_banner(model: str) -> None:
    """Print a hardware-aware startup panel with model recommendation."""
    sys_info = query_system_info()
    gpu = query_gpu_vram()
    img_on = query_comfyui_running()
    vid_on = query_video_running()

    lines: list[str] = []

    # CPU / RAM
    if sys_info:
        cpu_name = sys_info.get("cpu_name", "unknown")
        p = sys_info.get("cpu_physical", 0)
        lg = sys_info.get("cpu_logical", 0)
        lines.append(f"[bold]CPU[/bold]  {cpu_name}  [dim]{p}c / {lg}t[/dim]")
        ram_t = sys_info.get("ram_total_mb", 0)
        ram_a = sys_info.get("ram_available_mb", 0)
        if ram_t:
            lines.append(f"[bold]RAM[/bold]  {ram_t:,} MiB total  •  {ram_a:,} MiB free")

    # GPU
    if gpu:
        sd_parts = []
        if img_on: sd_parts.append("[yellow]A1111 active[/yellow]")
        if vid_on: sd_parts.append("[yellow]ComfyUI active[/yellow]")
        sd_tag = ("  " + "  ".join(sd_parts)) if sd_parts else ""
        lines.append(
            f"[bold]GPU[/bold]  {gpu['name']}  "
            f"{gpu['total_mb']:,} MiB total  •  {gpu['free_mb']:,} MiB free{sd_tag}"
        )
    else:
        lines.append("[bold]GPU[/bold]  [dim]not detected (CPU-only)[/dim]")

    # Recommendation
    lines.append("")
    lines.append("[bold cyan]Recommendation[/bold cyan]")
    rec = recommend_model_for_vram(gpu["total_mb"]) if gpu else None
    comfyui_on = img_on or vid_on

    if rec:
        marker = "[green]✓[/green]" if rec == model else "[yellow]→[/yellow]"
        note = "" if rec == model else f"  [dim](run [bold]/model {rec}[/bold] to switch)[/dim]"
        lines.append(f"  {marker}  [bold]{rec}[/bold]{note}")
        if comfyui_on and gpu:
            used_mb = gpu["total_mb"] - gpu["free_mb"]
            if used_mb > 1_000:
                lines.append(
                    f"  [dim]SD using ~{used_mb:,} MiB  •  "
                    f"[bold]/sd stop[/bold] to reclaim, or [bold]/sd image[/bold]/[bold]/sd video[/bold] to switch mode[/dim]"
                )
    elif gpu:
        lines.append("  [red]VRAM too low for any configured model[/red]")
        if comfyui_on and gpu:
            used_mb = gpu["total_mb"] - gpu["free_mb"]
            lines.append(f"  [dim]Try [bold]/sd stop[/bold] to reclaim ~{used_mb:,} MiB[/dim]")
    else:
        lines.append("  [dim]No GPU — CPU inference only (expect slow responses)[/dim]")
        ram_t = sys_info.get("ram_total_mb", 0) if sys_info else 0
        if ram_t >= 32_000:
            lines.append("  [dim]32 GB+ RAM available — CPU offloading may be viable[/dim]")

    console.print(Panel(
        "\n".join(lines),
        title="[cyan]System[/cyan]",
        border_style="cyan",
        expand=False,
    ))


# ── Backend Adapters ───────────────────────────────────────────────────────────


def pick_adapter(model: str, pipeline: Optional[str], cfg: dict) -> str:
    """Return adapter type: 'ollama', 'litellm', or 'pipeline'."""
    if pipeline:
        return "pipeline"
    if any(model.startswith(p) for p in CLOUD_MODEL_PREFIXES):
        return "litellm"
    return "ollama"


def stream_ollama(
    messages: list,
    model: str,
    cfg: dict,
    tools: Optional[list] = None,
) -> Generator[dict, None, None]:
    """
    Stream from Ollama /api/chat.
    Yields dicts: {"type": "token", "text": str}
                  {"type": "tool_call", "name": str, "arguments": dict}
                  {"type": "done", "message": dict}
    """
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {"num_ctx": 8192},
    }
    if tools:
        body["tools"] = tools

    try:
        resp = requests.post(
            f"{cfg['ollama_url']}/api/chat",
            json=body,
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        yield {"type": "error", "text": f"Cannot connect to Ollama at {cfg['ollama_url']}"}
        return
    except requests.HTTPError as e:
        yield {"type": "error", "text": f"Ollama error {e.response.status_code}: {e.response.text}"}
        return

    full_content = ""
    tool_calls = []

    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        try:
            chunk = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        msg = chunk.get("message", {})
        content = msg.get("content", "")
        if content:
            full_content += content
            yield {"type": "token", "text": content}

        # Ollama tool calls arrive in the final non-streaming message
        if chunk.get("done") and msg.get("tool_calls"):
            tool_calls = msg["tool_calls"]

    if tool_calls:
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", {})
            args = raw_args if isinstance(raw_args, dict) else json.loads(raw_args)
            yield {"type": "tool_call", "name": name, "arguments": args}
    else:
        yield {"type": "done", "message": {"role": "assistant", "content": full_content}}


def stream_openai_compat(
    messages: list,
    model: str,
    base_url: str,
    api_key: str,
    max_tokens: int = 4096,
) -> Generator[dict, None, None]:
    """
    Stream from any OpenAI-compatible endpoint (LiteLLM, pipelines).
    Yields same dict protocol as stream_ollama.
    """
    try:
        resp = requests.post(
            f"{base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": True,
            },
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
    except requests.ConnectionError:
        yield {"type": "error", "text": f"Cannot connect to {base_url}"}
        return
    except requests.HTTPError as e:
        body = e.response.text if e.response else "no body"
        yield {"type": "error", "text": f"API error {e.response.status_code}: {body}"}
        return

    full_content = ""
    for raw_line in resp.iter_lines():
        if not raw_line:
            continue
        decoded = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not decoded.startswith("data: "):
            continue
        data = decoded[6:]
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
            text = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if text:
                full_content += text
                yield {"type": "token", "text": text}
        except json.JSONDecodeError:
            continue

    yield {"type": "done", "message": {"role": "assistant", "content": full_content}}


# ── Project Indexer ────────────────────────────────────────────────────────────

_CLAUDE_MD_PROMPT = """\
You are analyzing a software project. Generate a CLAUDE.md file from the project \
files below. This file will be read by AI assistants to understand the project \
without needing to ingest every source file. Be concise, factual, and specific — \
do not invent details not present in the provided files.

Sections to include (omit any that don't apply):
## Overview
One paragraph: what the project does, primary language, framework.

## Key Files & Directories
Bulleted list of important paths and what they contain.

## Build & Run
Exact commands to install dependencies, build, and run.

## Architecture & Conventions
Important patterns, naming conventions, configuration approach.

## Dependencies
Key external packages and what they're used for.

Keep the output under 200 lines. Output only the Markdown — no preamble or explanation.

--- PROJECT FILES ---
{context}
"""

_README_PROMPT = """\
You are analyzing a software project. Generate a README.md from the project files \
below. Be concise and practical. Do not invent details not present in the files.

Include:
1. Project name as an H1 heading and a one-sentence description
2. Tech stack (inline text is fine)
3. Quick-start: install + run commands
4. Brief architecture/structure overview

{existing_section}\
--- PROJECT FILES ---
{context}
"""


def _detect_project_types(path: pathlib.Path) -> list[str]:
    types = []
    for pattern, label in PROJECT_SIGNALS:
        if "*" in pattern:
            if any(True for _ in path.glob(pattern)):
                types.append(label)
        else:
            if (path / pattern).exists():
                types.append(label)
    return types


def _find_project_roots(root: pathlib.Path) -> list[tuple[pathlib.Path, list[str]]]:
    results: list[tuple[pathlib.Path, list[str]]] = []
    for dirpath, dirnames, _ in os.walk(root):
        p = pathlib.Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        types = _detect_project_types(p)
        if types:
            results.append((p, types))
    return results


def _gather_context(project_path: pathlib.Path, types: list[str]) -> str:
    lines = [
        f"Project path: {project_path}",
        f"Detected types: {', '.join(types)}",
        "",
        "## Directory structure (top 2 levels, filtered)",
    ]
    try:
        for item in sorted(project_path.iterdir()):
            if item.name in SKIP_DIRS or item.name.startswith("."):
                continue
            lines.append(f"  {item.name}{'/' if item.is_dir() else ''}")
            if item.is_dir():
                try:
                    for sub in sorted(item.iterdir())[:12]:
                        if sub.name not in SKIP_DIRS:
                            lines.append(f"    {sub.name}{'/' if sub.is_dir() else ''}")
                except PermissionError:
                    pass
    except PermissionError:
        pass

    lines.append("")
    lines.append("## Key file contents")
    for pattern in CONTEXT_FILE_PATTERNS:
        candidates = (
            list(project_path.glob(pattern))
            if "*" in pattern
            else ([project_path / pattern] if (project_path / pattern).exists() else [])
        )
        for fp in candidates[:2]:
            if fp.is_file():
                try:
                    content = fp.read_text(encoding="utf-8", errors="ignore")
                    if len(content) > MAX_CONTEXT_CHARS_PER_FILE:
                        content = content[:MAX_CONTEXT_CHARS_PER_FILE] + "\n...(truncated)"
                    lines.append(f"### {fp.name}")
                    lines.append(content)
                    lines.append("")
                except Exception:
                    pass
    return "\n".join(lines)


def _call_local(messages: list, cfg: dict) -> str:
    """Synchronous (non-streaming) call to the local Ollama model."""
    try:
        resp = requests.post(
            f"{cfg['ollama_url']}/api/chat",
            json={
                "model": cfg["default_model"],
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": 16384},
            },
            timeout=300,
        )
        resp.raise_for_status()
        return resp.json().get("message", {}).get("content", "")
    except Exception as e:
        return f"[error calling local model: {e}]"


def _write_with_status(path: pathlib.Path, content: str, label: str) -> None:
    try:
        path.write_text(content, encoding="utf-8")
        console.print(f"  [green]wrote[/green] {label} ({len(content)} chars)")
    except Exception as e:
        console.print(f"  [red]error writing {label}: {e}[/red]")


def run_index_mode(root: pathlib.Path, cfg: dict) -> None:
    """Walk root, detect project directories, generate CLAUDE.md / update README.md."""
    console.print(f"\n[bold cyan]Indexing:[/bold cyan] {root}\n")
    projects = _find_project_roots(root)
    if not projects:
        console.print("[yellow]No projects detected.[/yellow]")
        return
    console.print(f"[dim]Found {len(projects)} project(s)[/dim]\n")

    for proj_path, types in projects:
        try:
            rel = proj_path.relative_to(root)
        except ValueError:
            rel = proj_path
        console.print(
            Panel(
                f"[bold]{rel or '.'}[/bold]\n[dim]{', '.join(types)}[/dim]",
                border_style="cyan",
                expand=False,
            )
        )

        context = _gather_context(proj_path, types)

        model_label = cfg["default_model"]

        # ── CLAUDE.md ──────────────────────────────────────────
        claude_md = proj_path / "CLAUDE.md"
        skip_claude = False
        if claude_md.exists():
            ans = console.input("  CLAUDE.md exists — overwrite? [y/N] ").strip().lower()
            skip_claude = ans not in ("y", "yes")
        if not skip_claude:
            console.print(f"  [dim]generating CLAUDE.md via {model_label}…[/dim]")
            content = _call_local(
                [{"role": "user", "content": _CLAUDE_MD_PROMPT.format(context=context)}],
                cfg,
            )
            _write_with_status(claude_md, content, "CLAUDE.md")

        # ── README.md ──────────────────────────────────────────
        readme = proj_path / "README.md"
        existing_readme = ""
        skip_readme = False
        if readme.exists():
            existing_readme = readme.read_text(encoding="utf-8", errors="ignore")
            if existing_readme.strip():
                ans = console.input("  README.md exists — update? [y/N] ").strip().lower()
                skip_readme = ans not in ("y", "yes")
        if not skip_readme:
            console.print(f"  [dim]generating README.md via {model_label}…[/dim]")
            existing_section = (
                f"Existing README (update or replace as appropriate):\n{existing_readme[:1500]}\n\n"
                if existing_readme.strip()
                else ""
            )
            content = _call_local(
                [
                    {
                        "role": "user",
                        "content": _README_PROMPT.format(
                            context=context,
                            existing_section=existing_section,
                        ),
                    }
                ],
                cfg,
            )
            _write_with_status(readme, content, "README.md")

        console.print()


# ── Token Budget ───────────────────────────────────────────────────────────────


class TokenBudget:
    """Tracks cumulative Claude API tokens (input + output) for the session."""

    def __init__(self, budget: int) -> None:
        self.budget = max(1, budget)
        self.used = 0

    def add(self, input_msgs: list, output_text: str) -> None:
        in_chars = sum(
            len(m.get("content") or "") for m in input_msgs if isinstance(m.get("content"), str)
        )
        self.used += (in_chars + len(output_text)) // 4

    @property
    def fraction(self) -> float:
        return self.used / self.budget

    @property
    def pct(self) -> int:
        return min(100, int(self.fraction * 100))

    def bar(self, width: int = 10) -> str:
        filled = int(self.fraction * width)
        return "█" * filled + "░" * (width - filled)

    def status_str(self) -> str:
        return f"{self.bar()} {self.pct}% ({self.used:,}/{self.budget:,} tok)"


def check_token_thresholds(budget: TokenBudget, session_state: dict) -> None:
    """Print warnings and toggle offline mode based on token budget usage."""
    f = budget.fraction
    if f >= TOKEN_LIMIT:
        console.print(
            f"[bold red]Token budget exhausted ({budget.status_str()}) — "
            "switching to offline mode.[/bold red]"
        )
        session_state["offline"] = True
    elif f >= TOKEN_OFFER:
        ans = (
            console.input(
                f"[bold yellow]⚠ Claude tokens at {budget.pct}% "
                f"({budget.status_str()}). Go offline? [y/N] [/bold yellow]"
            )
            .strip()
            .lower()
        )
        if ans in ("y", "yes"):
            session_state["offline"] = True
            console.print("[dim]Offline mode enabled — using local model only.[/dim]")
    elif f >= TOKEN_WARN:
        console.print(f"[yellow]⚠ Claude token usage: {budget.status_str()}[/yellow]")


# ── Rich UI Helpers ────────────────────────────────────────────────────────────

console = Console()


def print_header(
    model: str,
    pipeline: Optional[str],
    tools_on: bool,
    budget: Optional[TokenBudget] = None,
    offline: bool = False,
) -> None:
    active = f"pipeline:{pipeline}" if pipeline else model
    tools_str = "[green]on[/green]" if tools_on else "[dim]off[/dim]"
    mode_str = "[bold red]OFFLINE[/bold red]" if offline else "[dim]online[/dim]"
    tok_str = f"  •  tokens: {budget.status_str()}" if budget and budget.used > 0 else ""
    console.print(
        Panel(
            f"[bold cyan]clod[/bold cyan] [dim]v{__version__}[/dim]  •  "
            f"[bold]{active}[/bold]  •  tools: {tools_str}  •  {mode_str}{tok_str}\n"
            f"[dim]Type [bold]/help[/bold] for commands, [bold]Ctrl+D[/bold] to exit[/dim]",
            border_style="cyan",
            expand=False,
        )
    )


def print_help() -> None:
    pipeline_rows = "\n".join(
        f"  {name:<14} {cfg['local']:<36} → {cfg['claude']}"
        for name, cfg in PIPELINE_CONFIGS.items()
    )
    console.print(
        Panel(
            "\n".join(
                [
                    "[bold cyan]Slash commands:[/bold cyan]",
                    "  [yellow]/model [/yellow][dim]<name>[/dim]          switch model (ollama or litellm alias)",
                    "  [yellow]/pipeline [/yellow][dim]<name|off>[/dim]   use a two-stage pipeline",
                    "  [yellow]/tools [/yellow][dim][on|off][/dim]         toggle tool use",
                    "  [yellow]/offline [/yellow][dim][on|off][/dim]       toggle offline mode (local only)",
                    "  [yellow]/tokens[/yellow]                  show session Claude token usage",
                    "  [yellow]/system [/yellow][dim]<prompt>[/dim]        set system prompt",
                    "  [yellow]/clear[/yellow]                   clear conversation history",
                    "  [yellow]/save [/yellow][dim]<file>[/dim]            save conversation to JSON",
                    "  [yellow]/index [/yellow][dim][path][/dim]           index projects: generate CLAUDE.md + README",
                    "  [yellow]/gpu[/yellow]                     show GPU VRAM + optimal model recommendation",
                    "  [yellow]/sd [/yellow][dim][image|video|stop|start][/dim]  switch image/video mode or stop/start SD",
                    "  [yellow]/help[/yellow]                    show this message",
                    "  [yellow]/exit[/yellow] or [yellow]/quit[/yellow]            exit clod",
                    "",
                    "[bold cyan]Pipelines (local → claude):[/bold cyan]",
                    pipeline_rows,
                ]
            ),
            title="[cyan]help[/cyan]",
            border_style="cyan",
        )
    )


def print_tool_call(name: str, args: dict) -> None:
    args_str = json.dumps(args, indent=2)
    console.print(
        Panel(
            f"[bold]{name}[/bold]\n[dim]{args_str}[/dim]",
            title="[yellow]tool call[/yellow]",
            border_style="yellow",
        )
    )


def print_tool_result(name: str, result: str) -> None:
    preview = result[:500] + ("..." if len(result) > 500 else "")
    console.print(
        Panel(
            f"[dim]{preview}[/dim]",
            title=f"[green]result: {name}[/green]",
            border_style="green",
        )
    )


def stream_and_render(event_gen: Generator[dict, None, None]) -> tuple[str, list]:
    """
    Stream tokens with a live spinner, then render the full response as markdown.
    Returns (final_content, tool_calls_list).
    """
    tool_calls = []
    tokens: list[str] = []

    # Stream tokens while showing a live status indicator
    with console.status("[dim]generating…[/dim]", spinner="dots"):
        for event in event_gen:
            if event["type"] == "token":
                tokens.append(event["text"])
            elif event["type"] == "tool_call":
                tool_calls.append(event)
            elif event["type"] == "error":
                console.print(f"[red]{event['text']}[/red]")
                return "", []

    final_content = "".join(tokens)

    # Render once as markdown
    if final_content:
        console.print()
        console.print(Markdown(final_content))

    return final_content, tool_calls


# ── Inference Loop ─────────────────────────────────────────────────────────────


def infer(
    messages: list,
    model: str,
    pipeline: Optional[str],
    cfg: dict,
    tools_on: bool,
    offline: bool = False,
    budget: Optional[TokenBudget] = None,
    session_state: Optional[dict] = None,
) -> str:
    """
    Run one inference round (may loop for tool calls).
    Returns the final assistant message content.
    """
    # Offline: strip pipeline and redirect cloud models to local default
    if offline:
        pipeline = None
        if any(model.startswith(p) for p in CLOUD_MODEL_PREFIXES):
            model = cfg["default_model"]
            console.print(f"[dim][offline] using local model: {model}[/dim]")

    adapter = pick_adapter(model, pipeline, cfg)
    tools = TOOL_DEFINITIONS if (tools_on and adapter == "ollama") else None
    uses_claude = adapter in ("litellm", "pipeline")

    # Auto-pull Ollama model if not available locally
    if adapter == "ollama" and not ensure_ollama_model(model, cfg):
        return f"Could not obtain model '{model}'. Check Ollama connectivity."

    for _ in range(10):  # max tool call rounds
        if adapter == "ollama":
            gen = stream_ollama(messages, model, cfg, tools)
        elif adapter == "litellm":
            gen = stream_openai_compat(messages, model, cfg["litellm_url"], cfg["litellm_key"])
        else:  # pipeline
            gen = stream_openai_compat(messages, pipeline, cfg["pipelines_url"], cfg["litellm_key"])

        final_content, tool_calls = stream_and_render(gen)

        # Track Claude token usage after each round
        if uses_claude and budget is not None:
            budget.add(messages, final_content or "")
            if session_state is not None:
                check_token_thresholds(budget, session_state)

        if not tool_calls:
            return final_content

        # Add the assistant's (empty content) message with tool calls
        messages.append({"role": "assistant", "content": final_content or ""})

        # Execute each tool, add results
        for tc in tool_calls:
            print_tool_call(tc["name"], tc["arguments"])
            result = execute_tool(tc["name"], tc["arguments"], console, cfg)
            print_tool_result(tc["name"], result)
            messages.append(
                {
                    "role": "tool",
                    "name": tc["name"],
                    "content": result,
                }
            )

    return final_content or ""


# ── REPL ───────────────────────────────────────────────────────────────────────


def handle_slash(
    cmd: str,
    session_state: dict,
    messages: list,
) -> bool:
    """
    Handle a /command. Returns True if handled, False if unknown.
    Mutates session_state in place.
    """
    parts = cmd.strip().split(None, 1)
    verb = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if verb in ("/exit", "/quit"):
        console.print("[dim]bye[/dim]")
        sys.exit(0)

    elif verb == "/help":
        print_help()

    elif verb == "/clear":
        messages.clear()
        console.print("[dim]Conversation cleared.[/dim]")

    elif verb == "/model":
        if arg:
            session_state["model"] = arg
            session_state["pipeline"] = None
            console.print(f"[dim]Model → [bold]{arg}[/bold][/dim]")
            if not any(arg.startswith(p) for p in CLOUD_MODEL_PREFIXES):
                warmup_ollama_model(arg, session_state["cfg"])
        else:
            console.print(f"[dim]Current model: [bold]{session_state['model']}[/bold][/dim]")

    elif verb == "/pipeline":
        if arg.lower() == "off":
            session_state["pipeline"] = None
            console.print("[dim]Pipeline disabled.[/dim]")
        elif arg:
            session_state["pipeline"] = arg
            console.print(f"[dim]Pipeline → [bold]{arg}[/bold][/dim]")
        else:
            p = session_state.get("pipeline") or "none"
            console.print(f"[dim]Current pipeline: [bold]{p}[/bold][/dim]")

    elif verb == "/tools":
        if arg.lower() in ("on", "true", "1", ""):
            session_state["tools_on"] = True
            console.print("[dim]Tools [green]enabled[/green][/dim]")
        elif arg.lower() in ("off", "false", "0"):
            session_state["tools_on"] = False
            console.print("[dim]Tools [dim]disabled[/dim][/dim]")

    elif verb == "/system":
        if arg:
            session_state["system"] = arg
            # Update or insert system message
            if messages and messages[0]["role"] == "system":
                messages[0]["content"] = arg
            else:
                messages.insert(0, {"role": "system", "content": arg})
            console.print("[dim]System prompt updated.[/dim]")

    elif verb == "/save":
        fname = arg or "clod-conversation.json"
        try:
            with open(fname, "w") as f:
                json.dump(messages, f, indent=2)
            console.print(f"[dim]Saved to {fname}[/dim]")
        except Exception as e:
            console.print(f"[red]Save error: {e}[/red]")

    elif verb == "/offline":
        if arg.lower() in ("off", "false", "0"):
            session_state["offline"] = False
            console.print(
                "[dim]Offline mode [green]disabled[/green] — Claude calls re-enabled.[/dim]"
            )
        else:
            session_state["offline"] = True
            console.print("[dim]Offline mode [red]enabled[/red] — local model only.[/dim]")

    elif verb == "/tokens":
        budget: TokenBudget = session_state["budget"]
        if budget.used == 0:
            console.print("[dim]No Claude tokens used this session.[/dim]")
        else:
            console.print(f"[cyan]Claude tokens:[/cyan] {budget.status_str()}")

    elif verb == "/index":
        path = pathlib.Path(arg).expanduser() if arg else pathlib.Path(".")
        if not path.is_dir():
            console.print(f"[red]Not a directory: {path}[/red]")
        else:
            run_index_mode(path, session_state["cfg"])

    elif verb == "/gpu":
        gpu = query_gpu_vram()
        if gpu is None:
            console.print("[yellow]No NVIDIA GPU detected (nvidia-smi unavailable).[/yellow]")
        else:
            rec = recommend_model_for_vram(gpu["total_mb"])
            effective = gpu["total_mb"] - VRAM_CUDA_OVERHEAD_MB
            tier_rows = "\n".join(
                f"  {'[green]>>[/green]' if model_name == rec else '  '} "
                f"{label}  {model_name}"
                for min_mb, model_name, label in VRAM_TIERS
            )
            console.print(Panel(
                f"[bold]{gpu['name']}[/bold]\n"
                f"  Total:      {gpu['total_mb']:,} MiB\n"
                f"  Free now:   {gpu['free_mb']:,} MiB\n"
                f"  Effective:  {effective:,} MiB  (total − {VRAM_CUDA_OVERHEAD_MB} MiB overhead)\n\n"
                f"[bold cyan]Model tiers:[/bold cyan]\n{tier_rows}\n\n"
                f"[dim]Recommended:[/dim] [bold cyan]{rec or 'none (< 5 GB)'}[/bold cyan]  "
                f"  [dim](use [bold]/model {rec}[/bold] to switch)[/dim]",
                title="[cyan]GPU[/cyan]",
                border_style="cyan",
                expand=False,
            ))
            if arg.lower() == "use" and rec:
                session_state["model"] = rec
                session_state["pipeline"] = None
                console.print(f"[dim]Model → [bold]{rec}[/bold][/dim]")
                warmup_ollama_model(rec, session_state["cfg"])

    elif verb == "/sd":
        sub = arg.lower().strip()

        if sub in ("image", "video"):
            # ── Mode switch ───────────────────────────────────────────────
            current = session_state.get("sd_mode", cfg.get("sd_mode", "image"))
            if sub == current:
                console.print(f"[dim]Already in [bold]{sub}[/bold] mode.[/dim]")
            else:
                svc     = "AUTOMATIC1111 (localhost:7860)" if sub == "image" else "ComfyUI (localhost:8188)"
                console.print(
                    f"[dim]Switching to [bold]{sub}[/bold] mode → {svc}  "
                    f"(stopping {current}, restarting Open-WebUI…)[/dim]"
                )
                ok, msg = sd_switch_mode(sub, session_state["cfg"])
                if ok:
                    session_state["sd_mode"] = sub
                    gpu = query_gpu_vram()
                    note  = "" if sub == "image" else "  [dim]Use ComfyUI at localhost:8188 for video workflows.[/dim]"
                    owui  = "automatic1111" if sub == "image" else "comfyui"
                    rec   = recommend_model_for_vram(gpu["total_mb"]) if gpu else None
                    console.print(
                        Panel(
                            f"[green]Switched to [bold]{sub}[/bold] mode.[/green]\n"
                            f"  Service:   [bold]{svc}[/bold]\n"
                            f"  Open-WebUI image engine: [bold]{owui}[/bold]\n"
                            + (f"  GPU free:  [bold]{gpu['free_mb']:,} MiB[/bold]  •  "
                               f"LLM recommendation: [bold cyan]{rec or 'none'}[/bold cyan]\n"
                               if gpu else "")
                            + (note + "\n" if note else ""),
                            title=f"[cyan]SD mode → {sub}[/cyan]",
                            border_style="cyan",
                            expand=False,
                        )
                    )
                else:
                    console.print(f"[red]Switch failed: {msg}[/red]")

        elif sub == "stop":
            # ── Stop whichever service is running ─────────────────────────
            img_on   = query_comfyui_running()
            vid_on   = query_video_running()
            if not img_on and not vid_on:
                console.print("[dim]No SD service is running.[/dim]")
            else:
                ok, msg = comfyui_docker_action("stop")
                ok2, msg2 = (True, "") if not vid_on else comfyui_docker_action_video("stop")
                if ok and ok2:
                    console.print("[green]SD services stopped.[/green]")
                    gpu = query_gpu_vram()
                    if gpu:
                        rec = recommend_model_for_vram(gpu["total_mb"])
                        console.print(
                            f"[dim]GPU free: [bold]{gpu['free_mb']:,} MiB[/bold]  •  "
                            f"Recommended LLM: [bold cyan]{rec or 'none'}[/bold cyan][/dim]"
                        )
                else:
                    console.print(f"[red]Stop errors: {msg} {msg2}[/red]")

        elif sub == "start":
            # ── Restart last-active mode ──────────────────────────────────
            mode = session_state.get("sd_mode", session_state["cfg"].get("sd_mode", "image"))
            console.print(f"[dim]Starting [bold]{mode}[/bold] mode…[/dim]")
            ok, msg = sd_switch_mode(mode, session_state["cfg"])
            if ok:
                console.print(f"[green]SD started in [bold]{mode}[/bold] mode.[/green]")
            else:
                console.print(f"[red]Failed: {msg}[/red]")

        else:
            # ── Status ────────────────────────────────────────────────────
            img_on  = query_comfyui_running()
            vid_on  = query_video_running()
            gpu     = query_gpu_vram()
            mode    = session_state.get("sd_mode", "image")
            img_str = "[green]running[/green]" if img_on else "[dim]stopped[/dim]"
            vid_str = "[green]running[/green]" if vid_on else "[dim]stopped[/dim]"
            used    = (gpu["total_mb"] - gpu["free_mb"]) if gpu else 0
            console.print(Panel(
                f"[bold]Image[/bold]  AUTOMATIC1111  localhost:7860  {img_str}\n"
                f"[bold]Video[/bold]  ComfyUI        localhost:8188  {vid_str}\n"
                + (f"  GPU: {gpu['free_mb']:,} MiB free  •  ~{used:,} MiB in use\n" if gpu else "")
                + f"\n[dim]Active mode: [bold]{mode}[/bold][/dim]\n"
                f"[dim]  /sd image  — switch to AUTOMATIC1111 + restart Open-WebUI[/dim]\n"
                f"[dim]  /sd video  — switch to ComfyUI     + restart Open-WebUI[/dim]\n"
                f"[dim]  /sd stop   — stop all SD services (free VRAM for LLMs)[/dim]",
                title="[cyan]SD status[/cyan]",
                border_style="cyan",
                expand=False,
            ))

    else:
        return False

    return True


def run_repl(
    model: str,
    pipeline: Optional[str],
    system: Optional[str],
    tools_on: bool,
    cfg: dict,
) -> None:
    history_path().parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(history=FileHistory(str(history_path())))

    budget = TokenBudget(cfg.get("token_budget", 100_000))

    session_state = {
        "model": model,
        "pipeline": pipeline,
        "tools_on": tools_on,
        "system": system,
        "offline": False,
        "cfg": cfg,
        "budget": budget,
        "sd_mode": cfg.get("sd_mode", "image"),
    }

    messages: list = []
    if system:
        messages.append({"role": "system", "content": system})

    print_header(model, pipeline, tools_on, budget, offline=False)
    print_startup_banner(model)

    while True:
        try:
            active = session_state.get("pipeline") or session_state["model"]
            offline_tag = " [OFFLINE]" if session_state["offline"] else ""
            user_input = session.prompt(f"\n[{active}{offline_tag}] > ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]bye[/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            if not handle_slash(user_input, session_state, messages):
                console.print(f"[red]Unknown command: {user_input.split()[0]}[/red]")
            continue

        messages.append({"role": "user", "content": user_input})
        reply = infer(
            messages,
            session_state["model"],
            session_state.get("pipeline"),
            cfg,
            session_state["tools_on"],
            offline=session_state["offline"],
            budget=budget,
            session_state=session_state,
        )
        if reply:
            messages.append({"role": "assistant", "content": reply})


def run_oneshot(
    prompt: str,
    model: str,
    pipeline: Optional[str],
    system: Optional[str],
    tools_on: bool,
    cfg: dict,
) -> None:
    messages: list = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    infer(messages, model, pipeline, cfg, tools_on)


# ── Entry Point ────────────────────────────────────────────────────────────────


def main() -> None:
    cfg = load_config()

    parser = argparse.ArgumentParser(
        prog="clod",
        description="Local Claude CLI using Ollama + OpenWebUI Pipelines",
    )
    parser.add_argument(
        "-p", "--print", dest="prompt", metavar="PROMPT", help="One-shot mode: send prompt and exit"
    )
    parser.add_argument(
        "--model",
        "-m",
        default=cfg["default_model"],
        help=f"Model name (default: {cfg['default_model']})",
    )
    parser.add_argument(
        "--pipeline",
        metavar="NAME",
        help="Use a two-stage pipeline (code_review|reason_review|chat_assist)",
    )
    parser.add_argument("--system", "-s", metavar="PROMPT", help="System prompt for this session")
    parser.add_argument(
        "--tools",
        action="store_true",
        default=cfg["enable_tools"],
        help="Enable tool use (bash, file, web search)",
    )
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming output")
    parser.add_argument(
        "--index",
        metavar="PATH",
        nargs="?",
        const=".",
        help="Index projects under PATH (default: current dir): "
        "generate CLAUDE.md and update README.md using claude-sonnet",
    )
    parser.add_argument("--version", action="version", version=f"clod {__version__}")
    parser.add_argument(
        "--auto-model",
        action="store_true",
        help="Auto-select model based on detected GPU VRAM",
    )
    args = parser.parse_args()

    model = args.model
    pipeline = args.pipeline or cfg.get("pipeline")
    system = args.system
    tools_on = args.tools

    if args.auto_model or cfg.get("auto_model"):
        gpu = query_gpu_vram()
        if gpu:
            rec = recommend_model_for_vram(gpu["total_mb"])
            if rec and rec != model:
                console.print(Panel(
                    f"[bold]{gpu['name']}[/bold]  {gpu['total_mb']:,} MiB total  •  "
                    f"{gpu['free_mb']:,} MiB free\n"
                    f"[dim]Auto-selected:[/dim] [bold cyan]{rec}[/bold cyan]",
                    title="[cyan]GPU auto-model[/cyan]",
                    border_style="cyan",
                    expand=False,
                ))
                model = rec

    # Index mode
    if args.index is not None:
        root = pathlib.Path(args.index).expanduser().resolve()
        if not root.is_dir():
            console.print(f"[red]Not a directory: {root}[/red]")
            sys.exit(1)
        run_index_mode(root, cfg)
        return

    # One-shot from --print flag
    if args.prompt:
        run_oneshot(args.prompt, model, pipeline, system, tools_on, cfg)
        return

    # Pipe mode: stdin is not a TTY
    if not sys.stdin.isatty():
        prompt = sys.stdin.read().strip()
        if prompt:
            run_oneshot(prompt, model, pipeline, system, tools_on, cfg)
        return

    # Interactive REPL
    run_repl(model, pipeline, system, tools_on, cfg)


if __name__ == "__main__":
    main()
