#!/usr/bin/env python3
"""
clod — Local Claude CLI using Ollama + OpenWebUI Pipelines

Mimics the Claude CLI UX but runs entirely against the local Omni stack:
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
import re
import subprocess
import sys
import urllib.parse
from typing import Generator, Optional

import requests
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

__version__ = "1.0.0"

# ── Constants ──────────────────────────────────────────────────────────────────

CLOUD_MODEL_PREFIXES = ("claude-", "gpt-", "o1-", "o3-", "gemini-", "groq-", "together-")

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
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)"},
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
                    "append": {"type": "boolean", "description": "Append instead of overwrite (default false)"},
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
                    "count": {"type": "integer", "description": "Number of results to return (default 5)"},
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
    console.print(Panel(
        f"[bold yellow]$ {command}[/bold yellow]",
        title="[yellow]bash_exec[/yellow]",
        border_style="yellow",
    ))
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

# ── Rich UI Helpers ────────────────────────────────────────────────────────────

console = Console()


def print_header(model: str, pipeline: Optional[str], tools_on: bool) -> None:
    active = f"pipeline:{pipeline}" if pipeline else model
    tools_str = "[green]on[/green]" if tools_on else "[dim]off[/dim]"
    console.print(Panel(
        f"[bold cyan]clod[/bold cyan] [dim]v{__version__}[/dim]  •  "
        f"[bold]{active}[/bold]  •  tools: {tools_str}\n"
        f"[dim]Type [bold]/help[/bold] for commands, [bold]Ctrl+D[/bold] to exit[/dim]",
        border_style="cyan",
        expand=False,
    ))


def print_help() -> None:
    console.print(Panel(
        "\n".join([
            "[bold cyan]Slash commands:[/bold cyan]",
            "  [yellow]/model [/yellow][dim]<name>[/dim]          switch model (ollama or litellm alias)",
            "  [yellow]/pipeline [/yellow][dim]<name|off>[/dim]   use a two-stage pipeline",
            "  [yellow]/tools [/yellow][dim][on|off][/dim]         toggle tool use",
            "  [yellow]/system [/yellow][dim]<prompt>[/dim]        set system prompt",
            "  [yellow]/clear[/yellow]                   clear conversation history",
            "  [yellow]/save [/yellow][dim]<file>[/dim]            save conversation to JSON",
            "  [yellow]/help[/yellow]                    show this message",
            "  [yellow]/exit[/yellow] or [yellow]/quit[/yellow]            exit clod",
            "",
            "[bold cyan]Pipelines:[/bold cyan]",
            "  code_review    qwen2.5-coder:32b → claude-sonnet",
            "  reason_review  deepseek-r1:14b   → claude-sonnet",
            "  chat_assist    llama3.1:8b       → claude-sonnet",
        ]),
        title="[cyan]help[/cyan]",
        border_style="cyan",
    ))


def print_tool_call(name: str, args: dict) -> None:
    args_str = json.dumps(args, indent=2)
    console.print(Panel(
        f"[bold]{name}[/bold]\n[dim]{args_str}[/dim]",
        title="[yellow]tool call[/yellow]",
        border_style="yellow",
    ))


def print_tool_result(name: str, result: str) -> None:
    preview = result[:500] + ("…" if len(result) > 500 else "")
    console.print(Panel(
        f"[dim]{preview}[/dim]",
        title=f"[green]result: {name}[/green]",
        border_style="green",
    ))


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
) -> str:
    """
    Run one inference round (may loop for tool calls).
    Returns the final assistant message content.
    """
    adapter = pick_adapter(model, pipeline, cfg)
    tools = TOOL_DEFINITIONS if (tools_on and adapter == "ollama") else None

    for _ in range(10):  # max tool call rounds
        if adapter == "ollama":
            gen = stream_ollama(messages, model, cfg, tools)
        elif adapter == "litellm":
            gen = stream_openai_compat(messages, model, cfg["litellm_url"], cfg["litellm_key"])
        else:  # pipeline
            gen = stream_openai_compat(messages, pipeline, cfg["pipelines_url"], cfg["litellm_key"])

        final_content, tool_calls = stream_and_render(gen)

        if not tool_calls:
            return final_content

        # Add the assistant's (empty content) message with tool calls
        messages.append({"role": "assistant", "content": final_content or ""})

        # Execute each tool, add results
        for tc in tool_calls:
            print_tool_call(tc["name"], tc["arguments"])
            result = execute_tool(tc["name"], tc["arguments"], console, cfg)
            print_tool_result(tc["name"], result)
            messages.append({
                "role": "tool",
                "name": tc["name"],
                "content": result,
            })

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

    session_state = {
        "model": model,
        "pipeline": pipeline,
        "tools_on": tools_on,
        "system": system,
    }

    messages: list = []
    if system:
        messages.append({"role": "system", "content": system})

    print_header(model, pipeline, tools_on)

    while True:
        try:
            active = session_state.get("pipeline") or session_state["model"]
            user_input = session.prompt(f"\n[{active}] > ")
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
    parser.add_argument("-p", "--print", dest="prompt", metavar="PROMPT",
                        help="One-shot mode: send prompt and exit")
    parser.add_argument("--model", "-m", default=cfg["default_model"],
                        help=f"Model name (default: {cfg['default_model']})")
    parser.add_argument("--pipeline", metavar="NAME",
                        help="Use a two-stage pipeline (code_review|reason_review|chat_assist)")
    parser.add_argument("--system", "-s", metavar="PROMPT",
                        help="System prompt for this session")
    parser.add_argument("--tools", action="store_true", default=cfg["enable_tools"],
                        help="Enable tool use (bash, file, web search)")
    parser.add_argument("--no-stream", action="store_true",
                        help="Disable streaming output")
    parser.add_argument("--version", action="version", version=f"clod {__version__}")
    args = parser.parse_args()

    model = args.model
    pipeline = args.pipeline or cfg.get("pipeline")
    system = args.system
    tools_on = args.tools

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
