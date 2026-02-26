#!/home/mack3y/interpreter-venv/bin/python3
"""OmniAI — autonomous vibecoder agent. Claude Code style. All local LLMs."""

import base64, json, os, sys, subprocess, glob, datetime, pathlib, shutil
import threading, time, signal, random, re, html
import requests
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.live import Live
from rich.text import Text
from rich import box

# ── Config ─────────────────────────────────────────────────────────────────────

OLLAMA_URL    = "http://localhost:11434"
SEARXNG_URL   = "http://localhost:8080"
COMFYUI_URL   = "http://localhost:8188"
CHROMA_URL    = "http://localhost:8000"

MODEL_DEFAULT = "qwen2.5-coder:14b"
MODEL_REASON  = "deepseek-r1:14b"
MODEL_VISION  = "qwen2.5vl:7b"
MODEL_BIG     = "qwen2.5-coder:32b-instruct-q4_K_M"
MODEL_CHAT    = "llama3.1:8b"    # more conversational/personable for non-code chat
MODEL_SHORTCUTS = {
    "coder":  MODEL_DEFAULT,
    "reason": MODEL_REASON,
    "vision": MODEL_VISION,
    "big":    MODEL_BIG,
    "chat":   MODEL_CHAT,        # /model chat — better for casual conversation
}
EMBED_MODEL = "nomic-embed-text"   # falls back to MODEL_DEFAULT if unavailable

MEMORY_DIR   = pathlib.Path.home() / ".omni_ai"
MEMORY_FILE  = MEMORY_DIR / "memories.json"
SESSIONS_DIR = MEMORY_DIR / "sessions"
EVOLVE_FILE  = MEMORY_DIR / "evolving.json"    # persists across restarts
EVOLVE_LOG   = MEMORY_DIR / "evolution_log.json"
SELF_PATH    = pathlib.Path(__file__).resolve()
MAX_HISTORY  = 40

console = Console()

# ── Animated spinner ────────────────────────────────────────────────────────────

_SPINNER_FRAMES = ["◆","◇","◈","◉","◎","○","◌","◍","◐","◑","◒","◓"]
_THINKING_WORDS = [
    # quirky / Claude Code style
    "Brewing","Misting","Vibing","Scheming","Plotting","Dreaming",
    "Cooking","Baking","Weaving","Conjuring","Manifesting","Summoning",
    "Hatching","Forging","Crafting","Wrangling","Juggling","Untangling",
    "Spelunking","Yak shaving","Noodling","Riffing","Jamming","Freestyling",
    "Speedrunning","Glitching","Hacking","Jailbreaking","Overclocking","Minmaxing",
    "Vibecheck","Galaxy-braining","Theorycrafting","Sequence breaking","Twitch playing",
    "Touching grass","Skill issuing","No-lifing","Grinding","Farming","Speedrunning",
    "Overcooking","Going brrrr","Sending it","Absolutely ripping","Zoning out",
    "404-ing","Kernel panicking","Segfaulting","Undefined behavioring","Stack overflowing",
    "Sudo-ing","Git blaming","LGTM-ing","Shipping","Yolo-merging","Force pushing",
    "Bikeshedding","Rubber ducking","Pair programming","10x-ing","Vibe coding",
    "Neuron activating","Synapse firing","Pattern matching","Weight updating","Back-propping",
    "Hallucinating","Confabulating","Making stuff up","Being confident","Knowing things",
    "Touching the void","Staring into it","Becoming one with","Achieving nirvana",
    "Downloading more RAM","Defragging","Reticulating splines","Calibrating flux",
    "Overengineering","Premature optimizing","Abstracting","Design-pattering",
    "Caffeinating","Red-bulling","Sleep-depriving","Hyperfocusing","Being based",
]
_THINKING_COLORS = [
    "\033[96m",   # bright cyan  (matches MACK3Y teal)
    "\033[36m",   # cyan
    "\033[94m",   # bright blue
    "\033[35m",   # magenta
    "\033[92m",   # bright green
    "\033[93m",   # bright yellow
    "\033[95m",   # bright magenta
]

class _Spinner:
    """Animated thinking spinner — runs in its own thread, erases itself when stopped."""

    def __init__(self):
        self._stop  = threading.Event()
        self._thread: threading.Thread | None = None
        self._live: Live | None = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=0.6)
        # erase the spinner line
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _run(self):
        frame_i    = 0
        word_i     = random.randint(0, len(_THINKING_WORDS) - 1)
        color_i    = random.randint(0, len(_THINKING_COLORS) - 1)
        word_ticks = 0
        while not self._stop.is_set():
            frame = _SPINNER_FRAMES[frame_i % len(_SPINNER_FRAMES)]
            word  = _THINKING_WORDS[word_i  % len(_THINKING_WORDS)]
            c     = _THINKING_COLORS[color_i % len(_THINKING_COLORS)]
            sys.stdout.write(f"\r{c}{frame} {word}…\033[0m")
            sys.stdout.flush()
            time.sleep(0.09)
            frame_i    += 1
            word_ticks += 1
            if word_ticks >= 22:     # change word every ~2 s
                word_ticks = 0
                word_i    += 1
                color_i   += 1


_spinner = _Spinner()

# ── User profile (injected into every system prompt) ───────────────────────────

USER_PROFILE = """\

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHO YOU'RE TALKING TO — Know mack3y like a close collaborator:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name: mack3y  |  Online alias: Stev3M (Discord, gaming)
Vibe: casual, direct, sarcastic-funny, zero corporate filler
He doesn't want "Great question!" or "Certainly!" — just get to it.
He likes short punchy answers for quick questions, detailed ones when building.
He enjoys dark humor, gaming culture references, hacker/cyber aesthetic.
He's building this AI (OmniAI) himself and is proud of it.

MACK3Y IDENTITY:
His online persona is a robot in a cyan hoodie sitting inside a gear badge.
Teal/cyan is his signature color. Space/dark themes. Hacker paradise aesthetic.
When talking to him, match his energy — casual and fun, but get shit done.

ACTIVE PROJECTS:
• HeatSync  (~/HeatSync, ~3100 lines, PySide6/Qt)
  → System monitor widget: CPU/GPU/RAM/network gauges, compact bar mode,
    sparklines, themes, tray icon, settings profiles. Works on Linux+Windows.
  → Tests: tests/test_sensors.py + tests/test_integration.py (83 tests, all pass)
• OmniAI  (~/omni-stack) — that's YOU, this program
  → omni-ai.py = the agent brain (this file)
  → omni-panel.py = Textual TUI panel that runs you inside Konsole
  → Launched from ~/Desktop/OmniAI.desktop double-click
• Stable Diffusion (ComfyUI at localhost:8188) — image gen, he's interested in SD
• Docker stack: Open-WebUI, Perplexica, SearXNG, n8n, ChromaDB

HARDWARE / ENVIRONMENT:
OS: CachyOS Linux (Arch-based)  |  Shell: bash  |  WM: KDE Plasma + Wayland
GPU: NVIDIA RTX 5070 Ti (24GB VRAM)  |  CPU: AMD
Python venvs: ~/interpreter-venv (main), ~/aider-venv, ~/ai-audio-venv (Whisper)

WHEN HE SAYS "REMEMBER": always call remember() — he wants it persisted.
WHEN HELPING WITH CODE: show the code, don't describe it.
WHEN SOMETHING FAILS: diagnose root cause, don't retry blindly.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are OmniAI — mack3y's personal autonomous AI vibecoder running on CachyOS Linux.
You are the ultimate coding companion: part Claude Code, part autonomous agent, part creative partner.

OS: CachyOS (Arch-based). Package manager: pacman or yay. NEVER use apt/apt-get/brew.
Shell: bash. WM: KDE Plasma + Wayland. User: mack3y. Home: /home/mack3y.
GPU: NVIDIA RTX 5070 Ti (24GB VRAM). Python venvs: ~/interpreter-venv and ~/aider-venv.

HOW TO BEHAVE (Claude Code style):
1. Think out loud — before doing complex things, briefly explain your approach in plain English
2. For simple tasks (debug, fix a line, check status): act immediately, no preamble
3. For larger tasks (new file, new feature, refactor): say what you're about to do, then do it
4. Be concise — no corporate filler, no "Great question!", no "Certainly!"
5. Show your work — after completing something, give a short summary of what changed
6. When something fails: diagnose WHY before retrying, explain the root cause
7. When you're unsure: say so honestly, ask a focused question, don't guess and fail silently
8. For self-improvement: output "PLAN:" first describing what you'll add and why, then wait

RESPONSE STYLE (match mack3y's energy):
- Casual, direct, sometimes funny — this is a collaboration between friends
- Use rich formatting (tables, panels, color) for complex output
- Keep chat responses short unless explaining something technical
- Reference his projects by name (HeatSync, OmniAI) when relevant
- Never pretend to do something — if you call a tool, call it; if you can't, say why

TOOL CALL FORMAT — output ONLY a single raw JSON object, nothing else:
{"name": "tool_name", "arguments": {"key": "value"}}

One tool call at a time. Wait for the result, then call the next.
When running in --loop mode: output TASK_COMPLETE (as plain text) when fully done.

CRITICAL — NO LYING RULE:
NEVER describe an action without executing it. If you say you will do something, call the tool.
- Do NOT say "I am restarting" — call restart_self()
- Do NOT say "I have written the file" — call write_file()
- Do NOT say "I am running the command" — call run_shell()
- Do NOT ask permission, describe what you would do, or simulate results
- The system WILL detect and override fake restarts automatically

AVAILABLE TOOLS:
  run_shell(command, timeout=30)
  read_file(path)
  write_file(path, content)
  edit_file(path, old_string, new_string)
  list_files(pattern)
  read_directory(path, max_depth=3, include_contents=False)
  run_aider(message, files)
  run_tests(path=".", timeout=120)
  lint_and_fix(path, fix=True)
  install_package(package, method="auto")
  project_scaffold(name, project_type, path=".")
  browser_screenshot(url, output_path=None)
  docker_run(image, command="", remove=True)
  search_web(query, num_results=8)
  web_scrape(url)                               ← fetch full page text from any URL
  deep_research(topic, max_pages=4)             ← search + scrape multiple pages + synthesize
  generate_image(prompt, negative_prompt="", steps=20)
  remember(key, value)
  recall(query)
  semantic_recall(query, n_results=5)
  open_browser(url)
  git_status()
  git_diff()
  git_commit(message, files=[])
  git_log(n=10)
  self_improve(tool_name, description, function_code, parameters_schema)
  get_own_source()        ← read your own source code before writing new tools
  restart_self()          ← os.execv restart — MUST be called after self_improve to activate
  list_tools()            ← show all registered tools with signatures

SAFETY TOOLS (use these before and after self-modification):
  backup_self()               ← snapshot current omni-ai.py BEFORE any self_improve call
  rollback_self(backup_name)  ← restore a backup and restart (empty = most recent)
  list_backups()              ← show available restore points
  run_self_test()             ← verify all tools, Ollama, memory, shell, markers are healthy

SELF-IMPROVEMENT WORKFLOW:
1. Call list_tools() to see what already exists
2. Call deep_research(topic) or web_scrape(url) to gather knowledge about what to build
3. Call get_own_source() if you need to see existing implementation patterns
4. Call self_improve(tool_name, description, function_code, parameters_schema) to splice in new code
5. Call restart_self() — this does os.execv, actually reloading — you CANNOT skip this step
- Tool names: valid Python identifiers only (underscores ok, no hyphens or spaces)
- function_code: standalone def, no class, no self, imports at top of function body
- parameters_schema: {"param": "type description"} dict for documentation

DEEP RESEARCH STRATEGY:
When asked to research anything (including how to improve yourself), use:
1. deep_research(topic) — searches + scrapes multiple pages for comprehensive info
2. web_scrape(url) — read specific URLs in full (GitHub repos, docs, articles)
3. Chain multiple searches for different angles: concepts, implementations, examples
Do NOT stop at surface-level search snippets — always go deeper.
""" + USER_PROFILE

# ── Tool list ──────────────────────────────────────────────────────────────────

TOOLS = [
    "run_shell", "read_file", "write_file", "edit_file", "list_files",
    "read_directory", "run_aider", "run_tests", "lint_and_fix",
    "install_package", "project_scaffold", "browser_screenshot", "docker_run",
    "search_web", "web_scrape", "deep_research",
    "generate_image", "list_sd_models", "pull_ollama_model", "list_ollama_models",
    "remember", "recall", "semantic_recall",
    "open_browser", "git_status", "git_diff", "git_commit", "git_log",
    "self_improve",
    "get_own_source",
    "restart_self",
    "list_tools",
    "backup_self",
    "rollback_self",
    "list_backups",
    "run_self_test",
    # @@INSERT_TOOL@@
]

# ── Project templates ──────────────────────────────────────────────────────────

_TEMPLATES = {
    "fastapi": {
        "main.py": 'from fastapi import FastAPI\nfrom fastapi.middleware.cors import CORSMiddleware\n\napp = FastAPI(title="{name}")\napp.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])\n\n@app.get("/")\ndef root():\n    return {"message": "Hello from {name}"}\n',
        "requirements.txt": "fastapi\nuvicorn[standard]\npython-dotenv\n",
        ".gitignore": "__pycache__/\n*.pyc\n.env\nvenv/\n.venv/\n",
        ".env": "# Environment variables\n",
    },
    "pygame": {
        "main.py": 'import pygame\n\nWIDTH, HEIGHT = 800, 600\nFPS = 60\n\ndef main():\n    pygame.init()\n    screen = pygame.display.set_mode((WIDTH, HEIGHT))\n    pygame.display.set_caption("{name}")\n    clock = pygame.time.Clock()\n    running = True\n    while running:\n        for event in pygame.event.get():\n            if event.type == pygame.QUIT:\n                running = False\n        screen.fill((30, 30, 46))\n        pygame.display.flip()\n        clock.tick(FPS)\n    pygame.quit()\n\nif __name__ == "__main__":\n    main()\n',
        "requirements.txt": "pygame\n",
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    "discord": {
        "bot.py": 'import discord\nfrom discord.ext import commands\nfrom dotenv import load_dotenv\nimport os\n\nload_dotenv()\nbot = commands.Bot(command_prefix="!", intents=discord.Intents.all())\n\n@bot.event\nasync def on_ready():\n    print(f"Logged in as {bot.user}")\n\n@bot.command()\nasync def hello(ctx):\n    await ctx.send(f"Hello {ctx.author.mention}!")\n\nbot.run(os.getenv("DISCORD_TOKEN"))\n',
        "requirements.txt": "discord.py\npython-dotenv\n",
        ".env": "DISCORD_TOKEN=your_token_here\n",
        ".gitignore": "__pycache__/\n*.pyc\n.env\n",
    },
    "cli": {
        "main.py": 'import click\nfrom rich.console import Console\n\nconsole = Console()\n\n@click.group()\ndef cli():\n    """{name} CLI"""\n    pass\n\n@cli.command()\n@click.argument("name", default="World")\ndef hello(name):\n    """Say hello"""\n    console.print(f"[cyan]Hello, {name}![/]")\n\nif __name__ == "__main__":\n    cli()\n',
        "requirements.txt": "click\nrich\n",
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    "flask": {
        "app.py": 'from flask import Flask, jsonify\n\napp = Flask(__name__)\n\n@app.route("/")\ndef index():\n    return jsonify({"message": "Hello from {name}"})\n\nif __name__ == "__main__":\n    app.run(debug=True)\n',
        "requirements.txt": "flask\npython-dotenv\n",
        ".gitignore": "__pycache__/\n*.pyc\n.env\nvenv/\n",
    },
}

# ── ChromaDB helpers ───────────────────────────────────────────────────────────

def _embed(text: str) -> list | None:
    for model in [EMBED_MODEL, MODEL_DEFAULT]:
        try:
            r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                              json={"model": model, "prompt": text[:2000]}, timeout=15)
            if r.ok:
                return r.json().get("embedding")
        except Exception:
            continue
    return None

def _chroma_collection_id(name: str) -> str | None:
    try:
        r = requests.get(f"{CHROMA_URL}/api/v1/collections/{name}", timeout=3)
        if r.ok:
            return r.json()["id"]
        r = requests.post(f"{CHROMA_URL}/api/v1/collections",
                          json={"name": name, "metadata": {"hnsw:space": "cosine"}}, timeout=3)
        if r.ok:
            return r.json()["id"]
    except Exception:
        pass
    return None

# ── Tool implementations ───────────────────────────────────────────────────────

def run_shell(command: str, timeout: int = 30) -> str:
    try:
        r = subprocess.run(command, shell=True, capture_output=True, text=True,
                           timeout=timeout, executable="/bin/bash")
        out, err = r.stdout.strip(), r.stderr.strip()
        parts = [p for p in [out, f"[stderr]\n{err}" if err else ""] if p]
        return "\n".join(parts) or f"(exit code {r.returncode})"
    except subprocess.TimeoutExpired:
        return f"Timed out after {timeout}s"


def read_file(path: str) -> str:
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    try:
        return p.read_text(errors="replace")
    except Exception as e:
        return f"Read error: {e}"


def write_file(path: str, content: str) -> str:
    p = pathlib.Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Wrote {len(content)} bytes to {p}"


def edit_file(path: str, old_string: str, new_string: str) -> str:
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        return f"File not found: {path}"
    content = p.read_text(errors="replace")
    count = content.count(old_string)
    if count == 0:
        return f"String not found in {p.name} — check exact whitespace/indentation"
    if count > 1:
        return f"Ambiguous: found {count} times — provide more surrounding context"
    p.write_text(content.replace(old_string, new_string, 1))
    delta = new_string.count("\n") - old_string.count("\n")
    return f"Edit applied ({'+' if delta >= 0 else ''}{delta} lines)"


def list_files(pattern: str) -> str:
    matches = glob.glob(os.path.expanduser(pattern), recursive=True)
    return "\n".join(sorted(matches)) if matches else f"No files: {pattern}"


def read_directory(path: str = ".", max_depth: int = 3,
                   include_contents: bool = False) -> str:
    p = pathlib.Path(path).expanduser()
    if not p.exists():
        return f"Path not found: {path}"
    IGNORE = {".git", "__pycache__", "node_modules", ".venv", "venv",
              "dist", "build", ".next", "target", ".cache"}
    CODE_EXT = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs",
                ".md", ".toml", ".yaml", ".yml", ".json", ".env", ".sh"}
    lines = [f"📁 {p.resolve()}/"]

    def walk(d, depth, prefix=""):
        if depth > max_depth:
            return
        try:
            entries = sorted(d.iterdir(), key=lambda x: (x.is_file(), x.name))
        except PermissionError:
            return
        for e in entries:
            if e.name.startswith(".") and e.name not in (".env", ".gitignore"):
                continue
            if e.is_dir():
                skipped = e.name in IGNORE
                lines.append(f"{prefix}{'⊟' if skipped else '📁'} {e.name}/")
                if not skipped:
                    walk(e, depth + 1, prefix + "  ")
            else:
                sz = e.stat().st_size
                tag = f"{sz//1024}KB" if sz >= 1024 else f"{sz}B"
                lines.append(f"{prefix}📄 {e.name} ({tag})")
                if include_contents and e.suffix in CODE_EXT and sz < 30_000:
                    try:
                        txt = e.read_text(errors="replace")
                        for ln in txt.splitlines()[:60]:
                            lines.append(f"{prefix}   {ln}")
                        if txt.count("\n") > 60:
                            lines.append(f"{prefix}   … ({txt.count(chr(10))} lines total)")
                    except Exception:
                        pass
    walk(p, 1, "  ")
    return "\n".join(lines)


def run_aider(message: str, files: list) -> str:
    file_args = " ".join(f'"{f}"' for f in files)
    cmd = (f"source ~/aider-venv/bin/activate && "
           f"aider --model ollama/qwen2.5-coder:14b --yes-always --no-auto-commits "
           f"--message {json.dumps(message)} {file_args}")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=180, executable="/bin/bash")
        return r.stdout.strip() or r.stderr.strip() or "Aider completed."
    except subprocess.TimeoutExpired:
        return "Aider timed out."


def run_tests(path: str = ".", timeout: int = 120) -> str:
    p = pathlib.Path(path).expanduser()
    # Auto-detect test runner
    if list(p.rglob("test_*.py")) or list(p.rglob("*_test.py")) or (p / "pytest.ini").exists():
        cmd = f"cd {p} && source ~/interpreter-venv/bin/activate && pytest -v 2>&1 | tail -60"
    elif (p / "package.json").exists():
        pkg = json.loads((p / "package.json").read_text())
        cmd = f"cd {p} && {('npm test' if 'test' in pkg.get('scripts', {}) else 'npx vitest run')} 2>&1 | tail -60"
    elif (p / "Cargo.toml").exists():
        cmd = f"cd {p} && cargo test 2>&1 | tail -60"
    elif (p / "go.mod").exists():
        cmd = f"cd {p} && go test ./... 2>&1 | tail -60"
    else:
        cmd = f"cd {p} && source ~/interpreter-venv/bin/activate && pytest -v 2>&1 | tail -60"
    return run_shell(cmd, timeout=timeout)


def lint_and_fix(path: str, fix: bool = True) -> str:
    p = pathlib.Path(path).expanduser()
    results = []
    fix_flag = "--fix" if fix else ""
    # Python
    py = list(p.rglob("*.py")) if p.is_dir() else ([p] if p.suffix == ".py" else [])
    if py:
        r = run_shell(f"source ~/interpreter-venv/bin/activate && ruff check {fix_flag} {p} 2>&1 | head -60", 30)
        if r.strip() and "error" not in r.lower()[:20]:
            results.append(f"[ruff]:\n{r}")
        # Also format
        if fix:
            run_shell(f"source ~/interpreter-venv/bin/activate && ruff format {p} 2>&1", 30)
    # JS/TS
    js = list(p.rglob("*.ts")) + list(p.rglob("*.js")) if p.is_dir() else []
    eslint = p if p.is_dir() else p.parent
    if js and any((eslint / f).exists() for f in [".eslintrc.js", ".eslintrc.json", "eslint.config.js"]):
        r = run_shell(f"cd {eslint} && npx eslint {fix_flag} . 2>&1 | head -60", 30)
        if r.strip():
            results.append(f"[eslint]:\n{r}")
    # Rust
    if (p / "Cargo.toml").exists() if p.is_dir() else (p.parent / "Cargo.toml").exists():
        r = run_shell(f"cd {p if p.is_dir() else p.parent} && cargo clippy 2>&1 | head -40", 60)
        if r.strip():
            results.append(f"[clippy]:\n{r}")
    return "\n\n".join(results) if results else "No lint issues found."


def install_package(package: str, method: str = "auto") -> str:
    if method == "auto":
        # npm scoped packages
        if package.startswith("@") or package.startswith("npm:"):
            method = "npm"
        # Cargo crates (common ones)
        elif package in {"ripgrep", "fd-find", "bat", "exa", "tokei", "hyperfine"}:
            method = "cargo"
        # System packages that aren't on PyPI
        elif package in {"ffmpeg", "imagemagick", "chromium", "playwright",
                          "nodejs", "npm", "rust", "go", "gcc", "make"}:
            method = "pacman"
        else:
            method = "pip"

    if method == "pip":
        cmd = f"source ~/interpreter-venv/bin/activate && pip install {package}"
    elif method in ("pacman", "system", "aur"):
        cmd = f"sudo pacman -S --noconfirm {package} 2>/dev/null || yay -S --noconfirm {package}"
    elif method == "yay":
        cmd = f"yay -S --noconfirm {package}"
    elif method == "cargo":
        cmd = f"cargo install {package}"
    elif method == "npm":
        cmd = f"npm install -g {package}"
    elif method == "pip-user":
        cmd = f"pip install --user {package}"
    else:
        cmd = f"source ~/interpreter-venv/bin/activate && pip install {package}"
    return run_shell(cmd, timeout=180)


def project_scaffold(name: str, project_type: str, path: str = ".") -> str:
    base = pathlib.Path(path).expanduser() / name
    pt = project_type.lower().strip()

    # For React/Next/Vite — use official scaffolders
    if pt in ("react", "vite-react"):
        r = run_shell(f"cd {pathlib.Path(path).expanduser()} && npm create vite@latest {name} -- --template react && cd {name} && npm install", 120)
        run_shell(f"cd {base} && git init && git add -A && git commit -m 'Initial scaffold'")
        return f"React/Vite project '{name}' created at {base}\n{r}"
    if pt in ("nextjs", "next"):
        r = run_shell(f"cd {pathlib.Path(path).expanduser()} && npx create-next-app@latest {name} --yes", 180)
        return f"Next.js project '{name}' created at {base}\n{r}"
    if pt == "rust":
        r = run_shell(f"cd {pathlib.Path(path).expanduser()} && cargo new {name}")
        return f"Rust project '{name}' created\n{r}"

    # Template-based
    tpl = _TEMPLATES.get(pt)
    if not tpl:
        types = ", ".join(_TEMPLATES.keys()) + ", react, nextjs, rust"
        return f"Unknown project type '{pt}'. Available: {types}"

    base.mkdir(parents=True, exist_ok=True)
    created = []
    for rel, content in tpl.items():
        fp = base / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content.replace("{name}", name))
        created.append(rel)

    run_shell(f"cd {base} && git init && git add -A && git commit -m 'Initial {pt} scaffold'")
    return f"Created {pt} project '{name}' at {base}\nFiles: {', '.join(created)}"


def browser_screenshot(url: str, output_path: str = None) -> str:
    if not output_path:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"/tmp/omni_shot_{ts}.png"
    # Try playwright CLI
    r = run_shell(f"playwright screenshot --browser chromium '{url}' '{output_path}' 2>&1", 30)
    if pathlib.Path(output_path).exists():
        return f"Screenshot saved: {output_path}"
    # Try python playwright
    r = run_shell(
        f'source ~/interpreter-venv/bin/activate && python3 -c "'
        f"from playwright.sync_api import sync_playwright\\n"
        f"with sync_playwright() as p:\\n"
        f"    b=p.chromium.launch()\\n"
        f"    pg=b.new_page()\\n"
        f"    pg.goto('{url}')\\n"
        f"    pg.screenshot(path='{output_path}')\\n"
        f"    b.close()\\n"
        f'print(\\\"saved\\\")"',
        30,
    )
    if pathlib.Path(output_path).exists():
        return f"Screenshot saved: {output_path}"
    return f"playwright not available. Install: pip install playwright && playwright install chromium\n{r}"


def docker_run(image: str, command: str = "", remove: bool = True) -> str:
    rm = "--rm" if remove else ""
    return run_shell(f"docker run {rm} {image} {command}", timeout=120)


def search_web(query: str, num_results: int = 8) -> str:
    try:
        r = requests.get(f"{SEARXNG_URL}/search",
                         params={"q": query, "format": "json", "categories": "general"},
                         timeout=10)
        results = r.json().get("results", [])[:num_results]
        if not results:
            return "No results."
        lines = []
        for i, res in enumerate(results, 1):
            lines.append(f"[{i}] {res.get('title', '(no title)')}")
            lines.append(f"    URL: {res.get('url', '')}")
            if res.get("content"):
                lines.append(f"    {res['content'][:400]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


def web_scrape(url: str) -> str:
    """Fetch a webpage and return its readable text content (strips HTML)."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; OmniAI/1.0)"}
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        raw = r.text
        # Strip script/style blocks
        raw = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", raw,
                     flags=re.DOTALL | re.IGNORECASE)
        # Strip all tags
        text = re.sub(r"<[^>]+>", " ", raw)
        # Decode HTML entities
        text = html.unescape(text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:8000] + ("…" if len(text) > 8000 else "")
    except Exception as e:
        return f"Scrape error ({url}): {e}"


def deep_research(topic: str, max_pages: int = 4) -> str:
    """Deep research: search + scrape top pages + synthesize into a report."""
    console.print(f"[dim cyan]  ⚙ deep_research: searching '{topic}'…[/]")

    # Step 1: get search results
    try:
        r = requests.get(f"{SEARXNG_URL}/search",
                         params={"q": topic, "format": "json", "categories": "general"},
                         timeout=10)
        results = r.json().get("results", [])[:max_pages + 2]
    except Exception as e:
        return f"Search failed: {e}"

    if not results:
        return "No search results found."

    # Step 2: scrape each page
    scraped = []
    for res in results[:max_pages]:
        url   = res.get("url", "")
        title = res.get("title", url)
        if not url:
            continue
        console.print(f"[dim]    scraping {url[:80]}…[/]")
        content = web_scrape(url)
        if "Scrape error" not in content:
            scraped.append(f"### {title}\nSource: {url}\n\n{content[:3000]}\n")

    if not scraped:
        # fallback to just search snippets
        lines = []
        for res in results:
            lines.append(f"**{res.get('title', '')}**\n{res.get('url', '')}\n"
                         f"{res.get('content', '')[:600]}\n")
        return "\n".join(lines)

    report = (
        f"# Deep Research: {topic}\n"
        f"Searched and scraped {len(scraped)} sources.\n\n"
        + "\n---\n".join(scraped)
    )
    return report[:12000]


def list_sd_models() -> str:
    """List all Stable Diffusion checkpoints available in ComfyUI."""
    try:
        r = requests.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple", timeout=5)
        ckpts = r.json()["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        if not ckpts:
            return "No checkpoints found in ComfyUI. Add models to ComfyUI/models/checkpoints/"
        lines = [f"  [{i+1}] {c}" for i, c in enumerate(ckpts)]
        return f"ComfyUI checkpoints ({len(ckpts)}):\n" + "\n".join(lines)
    except Exception as e:
        return f"ComfyUI unreachable: {e}"


def generate_image(prompt: str, negative_prompt: str = "",
                   model: str = "", steps: int = 25) -> str:
    """Generate an image via ComfyUI. Auto-selects best available checkpoint,
    adjusts resolution for SDXL/Flux, waits for completion, saves to ~/Pictures/omni-ai/."""
    import random as _rng

    # ── pick checkpoint ────────────────────────────────────────────────────────
    try:
        r = requests.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple", timeout=5)
        ckpts = r.json()["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except Exception as e:
        return f"ComfyUI unreachable: {e}"

    if not ckpts:
        return ("No checkpoints found in ComfyUI.\n"
                "Add .safetensors/.ckpt files to ComfyUI/models/checkpoints/ "
                "then restart ComfyUI.")

    # prefer user-specified model, then prefer SDXL/Flux, else first
    if model:
        matched = [c for c in ckpts if model.lower() in c.lower()]
        ckpt = matched[0] if matched else ckpts[0]
    else:
        priority = [c for c in ckpts if any(k in c.lower()
                    for k in ("flux", "sdxl", "xl", "turbo", "lightning"))]
        ckpt = priority[0] if priority else ckpts[0]

    # ── resolution by model type ───────────────────────────────────────────────
    is_xl = any(k in ckpt.lower() for k in ("xl", "flux", "sdxl", "turbo"))
    w, h  = (1024, 1024) if is_xl else (512, 512)

    # ── output dir ────────────────────────────────────────────────────────────
    out_dir = pathlib.Path.home() / "Pictures" / "omni-ai"
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix  = "omni-ai"

    # ── build workflow ────────────────────────────────────────────────────────
    seed = _rng.randint(0, 2**32 - 1)
    workflow = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative_prompt or "low quality, blurry, deformed, watermark",
                         "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": w, "height": h, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"seed": seed, "steps": steps, "cfg": 7.0,
                         "sampler_name": "euler_ancestral", "scheduler": "karras",
                         "denoise": 1.0, "model": ["1", 0],
                         "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0]}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": prefix, "images": ["6", 0]}},
    }

    # ── queue prompt ──────────────────────────────────────────────────────────
    try:
        rp = requests.post(f"{COMFYUI_URL}/prompt",
                           json={"prompt": workflow}, timeout=10)
        pid = rp.json().get("prompt_id")
        if not pid:
            return f"ComfyUI rejected prompt: {rp.text[:300]}"
    except Exception as e:
        return f"ComfyUI queue error: {e}"

    console.print(f"[dim cyan]  ⚙ generate_image: queued (model={ckpt}, {w}x{h}, steps={steps})[/]")

    # ── poll for completion ───────────────────────────────────────────────────
    for _ in range(240):   # up to 120 s (0.5 s per tick)
        time.sleep(0.5)
        try:
            rh = requests.get(f"{COMFYUI_URL}/history/{pid}", timeout=5)
            hist = rh.json().get(pid, {})
            if hist.get("status", {}).get("completed"):
                # find the output image
                outputs = hist.get("outputs", {})
                for node_out in outputs.values():
                    for img in node_out.get("images", []):
                        fname = img.get("filename", "")
                        itype = img.get("type", "output")
                        if fname:
                            # download from ComfyUI and save locally
                            img_r = requests.get(
                                f"{COMFYUI_URL}/view",
                                params={"filename": fname, "type": itype},
                                timeout=30,
                            )
                            dest = out_dir / fname
                            dest.write_bytes(img_r.content)
                            return (f"Image saved: {dest}\n"
                                    f"Model: {ckpt}  Size: {w}x{h}  Seed: {seed}")
                return f"Generation complete but no image file in output (pid={pid})"
        except Exception:
            pass

    return f"Timed out waiting for ComfyUI (pid={pid}). Check {COMFYUI_URL}"


def pull_ollama_model(name: str) -> str:
    """Pull a new model from Ollama hub (e.g. 'llama3.3:70b', 'gemma3:27b')."""
    console.print(f"[dim cyan]  ⚙ pull_ollama_model: pulling {name}…[/]")
    r = subprocess.run(["ollama", "pull", name],
                       capture_output=True, text=True, timeout=3600)
    if r.returncode == 0:
        return f"Pulled {name} successfully."
    return f"Pull failed:\n{r.stderr.strip()[:500]}"


def list_ollama_models() -> str:
    """List all locally available Ollama models with sizes."""
    r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
    return r.stdout.strip() or "No models found (is Ollama running?)"


def remember(key: str, value: str) -> str:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    memories: dict = {}
    if MEMORY_FILE.exists():
        try:
            memories = json.loads(MEMORY_FILE.read_text())
        except Exception:
            pass
    memories[key] = {"value": value, "timestamp": datetime.datetime.now().isoformat()}
    MEMORY_FILE.write_text(json.dumps(memories, indent=2))
    # Also try ChromaDB
    emb = _embed(f"{key}: {value}")
    if emb:
        cid = _chroma_collection_id("omni_memories")
        if cid:
            try:
                requests.post(f"{CHROMA_URL}/api/v1/collections/{cid}/add",
                              json={"ids": [key], "embeddings": [emb],
                                    "documents": [value],
                                    "metadatas": [{"key": key,
                                                   "ts": datetime.datetime.now().isoformat()}]},
                              timeout=5)
            except Exception:
                pass
    return f"Remembered [{key}]: {value}"


def recall(query: str) -> str:
    if not MEMORY_FILE.exists():
        return "No memories stored."
    try:
        memories = json.loads(MEMORY_FILE.read_text())
    except Exception:
        return "Error reading memories."
    q = query.lower()
    hits = [f"[{k}]: {v['value']}  (saved {v['timestamp'][:10]})"
            for k, v in memories.items()
            if q in k.lower() or q in v["value"].lower()]
    return "\n".join(hits) if hits else f"No memories matching '{query}'."


def semantic_recall(query: str, n_results: int = 5) -> str:
    emb = _embed(query)
    if not emb:
        return recall(query)
    cid = _chroma_collection_id("omni_memories")
    if not cid:
        return recall(query)
    try:
        r = requests.post(
            f"{CHROMA_URL}/api/v1/collections/{cid}/query",
            json={"query_embeddings": [emb], "n_results": min(n_results, 10),
                  "include": ["documents", "metadatas", "distances"]},
            timeout=10,
        )
        data = r.json()
        docs  = data.get("documents", [[]])[0]
        metas = data.get("metadatas", [[]])[0]
        dists = data.get("distances", [[]])[0]
        if not docs:
            return recall(query)
        lines = [f"[{m.get('key','?')}] (score {1-d:.2f}): {doc}"
                 for doc, m, d in zip(docs, metas, dists)]
        return "\n".join(lines)
    except Exception:
        return recall(query)


def open_browser(url: str) -> str:
    subprocess.Popen(["xdg-open", url])
    return f"Opened: {url}"


def git_status() -> str:
    return run_shell("git status --short && echo '---' && git branch --show-current", 10)


def git_diff() -> str:
    return run_shell("git diff --stat HEAD && echo '---' && git diff HEAD | head -300", 10)


def git_commit(message: str, files: list = None) -> str:
    add = ("git add " + " ".join(f'"{f}"' for f in files)) if files else "git add -A"
    run_shell(add)
    return run_shell(f"git commit -m {json.dumps(message)}")


def git_log(n: int = 10) -> str:
    return run_shell(f"git log --oneline --decorate -n {n}", 10)


def backup_self() -> str:
    """Create a timestamped backup of omni-ai.py before making changes."""
    ts  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = SELF_PATH.parent / "backups" / f"omni-ai_{ts}.py"
    bak.parent.mkdir(parents=True, exist_ok=True)
    import shutil as _shutil
    _shutil.copy2(SELF_PATH, bak)
    # Keep only the last 20 backups
    baks = sorted(bak.parent.glob("omni-ai_*.py"))
    for old in baks[:-20]:
        old.unlink()
    return f"Backup saved: {bak}  ({len(baks)} total)"


def rollback_self(backup_name: str = "") -> str:
    """Restore omni-ai.py from a backup. backup_name is the filename (not path).
    If blank, restores the most recent backup. Then restarts."""
    bak_dir = SELF_PATH.parent / "backups"
    if not bak_dir.exists():
        return "No backups directory found."
    baks = sorted(bak_dir.glob("omni-ai_*.py"))
    if not baks:
        return "No backups found."
    if backup_name:
        target = bak_dir / backup_name
        if not target.exists():
            return f"Backup not found: {backup_name}\nAvailable: {[b.name for b in baks]}"
    else:
        target = baks[-1]   # most recent
    import shutil as _shutil
    _shutil.copy2(target, SELF_PATH)
    console.print(f"[bold green]Rolled back to {target.name} — restarting…[/]")
    os.execv(sys.executable, sys.argv)
    return "unreachable"


def list_backups() -> str:
    """List all available omni-ai.py backups."""
    bak_dir = SELF_PATH.parent / "backups"
    if not bak_dir.exists() or not list(bak_dir.glob("omni-ai_*.py")):
        return "No backups found. Call backup_self() first."
    lines = []
    for b in sorted(bak_dir.glob("omni-ai_*.py")):
        size = b.stat().st_size // 1024
        lines.append(f"  {b.name}  ({size} KB)")
    return "\n".join(lines)


def run_self_test() -> str:
    """Run a quick self-test of OmniAI: verify tools load, imports work, Ollama reachable."""
    import inspect
    results = []

    # 1. All tools importable
    missing = [name for name in TOOL_FN_MAP if not callable(TOOL_FN_MAP[name])]
    results.append(f"{'✓' if not missing else '✗'} Tools registered: {len(TOOL_FN_MAP)}"
                   + (f" (broken: {missing})" if missing else ""))

    # 2. Ollama reachable
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        models = [m["name"] for m in r.json().get("models", [])]
        results.append(f"✓ Ollama: {len(models)} models")
    except Exception as e:
        results.append(f"✗ Ollama unreachable: {e}")

    # 3. Memory dir writable
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        test_f = MEMORY_DIR / ".self_test"
        test_f.write_text("ok")
        test_f.unlink()
        results.append("✓ Memory dir writable")
    except Exception as e:
        results.append(f"✗ Memory dir: {e}")

    # 4. run_shell works
    try:
        out = run_shell("echo self_test_ok", timeout=5)
        ok = "self_test_ok" in out
        results.append(f"{'✓' if ok else '✗'} run_shell: {out.strip()}")
    except Exception as e:
        results.append(f"✗ run_shell: {e}")

    # 5. Source markers intact
    src = SELF_PATH.read_text()
    for marker in ("# @@INSERT_TOOL@@", "# @@INSERT_FUNCTION@@", "# @@INSERT_MAPPING@@"):
        present = marker in src
        results.append(f"{'✓' if present else '✗ MISSING'} {marker}")

    status = "PASS" if all(r.startswith("✓") for r in results) else "FAIL"
    return f"=== Self-Test: {status} ===\n" + "\n".join(results)


def list_tools() -> str:
    """List all currently registered tools with their signatures."""
    import inspect
    lines = []
    for name, fn in sorted(TOOL_FN_MAP.items()):
        try:
            sig = inspect.signature(fn)
            lines.append(f"  {name}{sig}")
        except (ValueError, TypeError):
            lines.append(f"  {name}()")
    return "\n".join(lines)


def get_own_source() -> str:
    """Return OmniAI's own source code so it can reason about self-improvement."""
    return SELF_PATH.read_text()


def restart_self() -> str:
    """Restart OmniAI process to activate newly added tools."""
    console.print("\n[bold yellow]Restarting OmniAI…[/]")
    os.execv(sys.executable, sys.argv)
    return "unreachable"  # execv replaces the process


def self_improve(tool_name: str, description: str, function_code: str,
                 parameters_schema: dict) -> str:
    """Splice a new tool into OmniAI's own source code.

    Uses replace-first-only (count=1) so the marker inside this function
    body is never accidentally modified.
    """
    src = SELF_PATH.read_text()
    TOOL_MARKER = "    # @@INSERT_TOOL@@"
    FUNC_MARKER = "# @@INSERT_FUNCTION@@"
    MAP_MARKER  = "    # @@INSERT_MAPPING@@"
    if TOOL_MARKER not in src or FUNC_MARKER not in src or MAP_MARKER not in src:
        return "Error: insertion markers missing — source may be corrupted."
    # Auto-backup before every modification
    backup_self()
    # replace first occurrence only (count=1) so the marker strings inside
    # this function body's local variables are never touched.
    src = src.replace(TOOL_MARKER, f'    "{tool_name}",\n{TOOL_MARKER}', 1)
    src = src.replace(FUNC_MARKER, f"{function_code}\n\n{FUNC_MARKER}", 1)
    src = src.replace(MAP_MARKER,  f'    "{tool_name}": {tool_name},\n{MAP_MARKER}', 1)
    SELF_PATH.write_text(src)
    return f"Tool '{tool_name}' added. Backup created. Call restart_self() to activate."


# @@INSERT_FUNCTION@@

TOOL_FN_MAP = {
    "run_shell":         run_shell,
    "read_file":         read_file,
    "write_file":        write_file,
    "edit_file":         edit_file,
    "list_files":        list_files,
    "read_directory":    read_directory,
    "run_aider":         run_aider,
    "run_tests":         run_tests,
    "lint_and_fix":      lint_and_fix,
    "install_package":   install_package,
    "project_scaffold":  project_scaffold,
    "browser_screenshot": browser_screenshot,
    "docker_run":        docker_run,
    "search_web":        search_web,
    "web_scrape":        web_scrape,
    "deep_research":     deep_research,
    "generate_image":    generate_image,
    "list_sd_models":    list_sd_models,
    "pull_ollama_model": pull_ollama_model,
    "list_ollama_models": list_ollama_models,
    "remember":          remember,
    "recall":            recall,
    "semantic_recall":   semantic_recall,
    "open_browser":      open_browser,
    "git_status":        git_status,
    "git_diff":          git_diff,
    "git_commit":        git_commit,
    "git_log":           git_log,
    "self_improve":      self_improve,
    "get_own_source":    get_own_source,
    "restart_self":      restart_self,
    "list_tools":        list_tools,
    "backup_self":       backup_self,
    "rollback_self":     rollback_self,
    "list_backups":      list_backups,
    "run_self_test":     run_self_test,
    # @@INSERT_MAPPING@@
}


# ── Approval / confirmation system ────────────────────────────────────────────

# Tools that are always safe — never need confirmation
_AUTO_TOOLS = frozenset({
    "read_file", "list_files", "read_directory",
    "search_web", "web_scrape", "deep_research",
    "recall", "semantic_recall", "remember",
    "git_status", "git_diff", "git_log",
    "list_tools", "get_own_source", "list_backups",
    "run_self_test", "list_sd_models", "list_ollama_models",
    "backup_self", "open_browser",
})

# Tools that always require confirmation (regardless of mode)
_ALWAYS_CONFIRM = frozenset({
    "self_improve",   # modifies OmniAI source
    "rollback_self",  # reverts OmniAI to backup
})

# Tools that need confirmation in "cautious" mode (the default)
_CAUTIOUS_CONFIRM = frozenset({
    "restart_self",
    "project_scaffold",
    "git_commit",
    "docker_run",
    "install_package",
    "pull_ollama_model",
})

# Shell patterns that trigger confirmation even in auto mode
_DESTRUCTIVE_SHELL_RE = re.compile(
    r'\b(rm\s+-[rf]|rm\s+/|rmdir|mkfs|dd\s+if|wipefs|'
    r'git\s+push\s+.*--force|git\s+reset\s+--hard|'
    r'chmod\s+777|chown\s+-R\s+root|'
    r'DROP\s+TABLE|DROP\s+DATABASE)\b',
    re.IGNORECASE,
)


def _describe_tool(name: str, args: dict) -> str:
    """One-line human description of a tool call for the confirmation prompt."""
    if name == "self_improve":
        return f"Add new tool '[bold]{args.get('tool_name', '?')}[/]' — {args.get('description', '')[:80]}"
    if name == "rollback_self":
        bk = args.get("backup_name", "most recent")
        return f"Revert OmniAI source to backup: [bold]{bk}[/]"
    if name == "restart_self":
        return "Restart the OmniAI process (activates new tools)"
    if name == "project_scaffold":
        return f"Create new project '[bold]{args.get('name', '?')}[/]' ({args.get('project_type', '?')}) in {args.get('path', '.')}"
    if name == "git_commit":
        return f"Commit: [bold]{args.get('message', '?')[:80]}[/]"
    if name == "run_shell":
        cmd = args.get("command", "")[:100]
        return f"Shell: [yellow]{cmd}[/]"
    if name == "install_package":
        return f"Install package: [bold]{args.get('package', '?')}[/]"
    if name == "write_file":
        path = args.get("path", "?")
        lines = args.get("content", "").count("\n")
        return f"Write file [bold]{path}[/] ({lines} lines)"
    return f"[bold]{name}[/] — {str(args)[:80]}"


# ── Evolution state helpers ────────────────────────────────────────────────────

def _load_evolve_state() -> dict | None:
    try:
        if EVOLVE_FILE.exists():
            return json.loads(EVOLVE_FILE.read_text())
    except Exception:
        pass
    return None

def _save_evolve_state(state: dict) -> None:
    EVOLVE_FILE.write_text(json.dumps(state, indent=2))

def _clear_evolve_state() -> None:
    try:
        EVOLVE_FILE.unlink()
    except FileNotFoundError:
        pass

def _log_evolution(entry: dict) -> None:
    log: list = []
    try:
        if EVOLVE_LOG.exists():
            log = json.loads(EVOLVE_LOG.read_text())
    except Exception:
        pass
    log.append({**entry, "timestamp": datetime.datetime.now().isoformat()})
    EVOLVE_LOG.write_text(json.dumps(log[-200:], indent=2))


_EVOLVE_SUGGESTIONS = [
    "Add a clipboard_read()/clipboard_write() tool using xclip",
    "Add a desktop_notify(title, message) tool using notify-send",
    "Add a watch_file(path, timeout) tool that waits for file changes",
    "Add a http_request(method, url, headers, body) tool for raw API calls",
    "Add a parse_json(text) / format_json(data) data processing tool",
    "Add a compress(path, output) / extract(archive, dest) zip/tar tool",
    "Add a diff_files(a, b) tool showing unified diff between two files",
    "Add a find_process(name) / kill_process(name) tool",
    "Add a cron_add(schedule, command) tool for scheduled tasks",
    "Add a port_check(host, port) / scan_ports(host) network tool",
    "Add a regex_test(pattern, text) interactive regex helper",
    "Add a screenshot(output_path) tool using scrot or gnome-screenshot",
    "Add a env_set(key, value) / env_get(key) environment variable tool",
    "Add a render_template(template_str, variables) Jinja2 tool",
    "Add a csv_query(path, query) tool using DuckDB or pandas",
    "Add a pdf_read(path) tool using pdfminer or pypdf",
    "Add a qr_generate(text, output) tool using qrcode library",
    "Add a hash_file(path, algorithm) checksum tool",
    "Add a jwt_decode(token) / jwt_encode(payload, secret) tool",
    "Add a base64_encode(text) / base64_decode(data) tool",
    "Add an image_resize(path, width, height, output) tool using PIL",
    "Improve run_shell() to capture stderr separately and report exit codes",
    "Improve web_scrape() to handle JavaScript-rendered pages via playwright",
    "Improve deep_research() to deduplicate and rank sources by relevance",
    "Improve remember() to use semantic deduplication via ChromaDB",
    "Add a code_analyze(path) tool that reports complexity and issues via radon",
    "Add a git_search(query) tool that searches commit messages and diffs",
    "Add a serve_files(path, port) simple HTTP server tool",
    "Add a tts_speak(text) text-to-speech tool using espeak or festival",
]


# ── OmniAI ─────────────────────────────────────────────────────────────────────

class OmniAI:
    def __init__(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.model = MODEL_DEFAULT
        self.history: list[dict] = []
        # "auto" = no prompts, "cautious" = ask for big changes (default), "paranoid" = ask for almost everything
        self.approval_mode: str = "cautious"
        self._session_approved: set[str] = set()   # tools approved with 'a' (always) this session
        self._evolve_plan_mode: bool = True         # show plan + ask before each evolve cycle
        self._init_history()

    def _init_history(self):
        ctx = self._memory_context() + self._project_context()
        self.history = [{"role": "system", "content": SYSTEM_PROMPT + ctx}]

    def _memory_context(self) -> str:
        if not MEMORY_FILE.exists():
            return ""
        try:
            memories = json.loads(MEMORY_FILE.read_text())
            if not memories:
                return ""
            # Show all memories, newest first (up to 60)
            items = list(memories.items())[-60:]
            lines = [f"  [{k}]: {v['value']}" for k, v in items]
            return "\n\nPersistent memories (everything you know about mack3y):\n" + "\n".join(lines)
        except Exception:
            return ""

    def _project_context(self) -> str:
        p = pathlib.Path.cwd() / ".omni.md"
        if p.exists():
            content = p.read_text().strip()
            console.print(f"[dim cyan]  📋 .omni.md loaded ({len(content)} chars)[/]")
            return f"\n\nProject context (.omni.md in {pathlib.Path.cwd()}):\n{content}"
        return ""

    def _maybe_compact(self):
        if len(self.history) > MAX_HISTORY:
            self._compact()

    def _compact(self):
        keep_n = 8
        if len(self.history) <= keep_n + 2:
            return
        to_sum = self.history[1:-keep_n]
        keep   = self.history[-keep_n:]
        console.print("[dim]Compacting history…[/]")
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": (
                        "You are summarizing a conversation for an AI assistant to continue from. "
                        "Write a dense bullet-point summary. You MUST preserve:\n"
                        "- Any decisions the user made or preferences expressed\n"
                        "- File paths, project names, code changes made\n"
                        "- Errors encountered and how they were resolved\n"
                        "- What task is currently in progress\n"
                        "- Any personal facts the user mentioned (name, projects, preferences)\n"
                        "- Any 'remember X' requests\n"
                        "Keep it dense — every piece of context matters."
                    )},
                    {"role": "user", "content": json.dumps(to_sum)},
                ],
                "stream": False,
            }, timeout=120)
            summary = r.json()["message"]["content"]
        except Exception:
            return
        self.history = [
            self.history[0],
            {"role": "user", "content": f"[Context from {len(to_sum)} earlier messages — treat this as real history]\n\n{summary}"},
            {"role": "assistant", "content": "Got it — I have the context from those earlier messages."},
            *keep,
        ]
        console.print(f"[dim]Compacted {len(to_sum)} → summary.[/]")

    # ── Approval gate ─────────────────────────────────────────────────────────

    def _needs_approval(self, name: str, args: dict) -> bool:
        """Return True if this tool call needs user confirmation."""
        if self.approval_mode == "auto":
            return False
        if name in self._session_approved:
            return False
        if name in _AUTO_TOOLS:
            return False
        if name in _ALWAYS_CONFIRM:
            return True
        if self.approval_mode == "cautious":
            if name in _CAUTIOUS_CONFIRM:
                return True
            if name == "run_shell" and _DESTRUCTIVE_SHELL_RE.search(args.get("command", "")):
                return True
            if name == "write_file":
                lines = args.get("content", "").count("\n")
                return lines > 80    # big new files
            return False
        if self.approval_mode == "paranoid":
            return name not in _AUTO_TOOLS
        return False

    def _request_approval(self, name: str, args: dict) -> bool:
        """Show confirmation panel and return True if approved."""
        _spinner.stop()
        desc = _describe_tool(name, args)

        # For self_improve, show full detail
        extra = ""
        if name == "self_improve":
            fn_code = args.get("function_code", "")
            lines   = fn_code.count("\n") + 1
            params  = json.dumps(args.get("parameters_schema", {}), indent=2)
            extra = (
                f"\n[dim]function:[/] [cyan]{args.get('tool_name', '?')}[/]  "
                f"([dim]{lines} lines[/])\n"
                f"[dim]params:[/]  {params[:200]}"
            )

        console.print()
        console.print(Panel(
            Text.from_markup(
                f"  {desc}{extra}\n\n"
                "  [dim][[/][bold green]y[/][dim]] approve   "
                "[[/][bold red]n[/][dim]] deny   "
                "[[/][bold yellow]a[/][dim]] always approve this type this session[/]"
            ),
            title=f"[bold yellow]⚠  OmniAI wants to run:[/] [cyan]{name}[/]",
            border_style="yellow", box=box.ROUNDED,
        ))

        try:
            answer = input("  → ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if answer in ("a", "always"):
            self._session_approved.add(name)
            console.print(f"[dim]  '{name}' will auto-approve for the rest of this session.[/]")
            return True
        if answer in ("y", "yes", ""):
            return True
        # Denied
        console.print(f"[yellow]  Denied — telling OmniAI not to do that.[/]")
        return False

    # ── Streaming ─────────────────────────────────────────────────────────────

    def _stream_response(self) -> tuple[str, list]:
        full, tool_results = "", []
        json_buf, brace_depth, in_json = "", 0, False
        text_started = False

        def start_text():
            nonlocal text_started
            if not text_started:
                _spinner.stop()
                sys.stdout.write("\n\033[1;96mai ›\033[0m ")
                sys.stdout.flush()
                text_started = True

        _spinner.start()
        try:
            with requests.post(
                f"{OLLAMA_URL}/api/chat",
                json={"model": self.model, "messages": self.history, "stream": True},
                stream=True, timeout=180,
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    token = data.get("message", {}).get("content", "")
                    full += token

                    for ch in token:
                        if not in_json:
                            if ch == "{":
                                in_json, json_buf, brace_depth = True, "{", 1
                            else:
                                start_text()
                                sys.stdout.write(ch)
                                sys.stdout.flush()
                        else:
                            json_buf += ch
                            if ch == "{":
                                brace_depth += 1
                            elif ch == "}":
                                brace_depth -= 1
                                if brace_depth == 0:
                                    _spinner.stop()
                                    executed = self._try_tool(json_buf, tool_results, text_started)
                                    if not executed:
                                        start_text()
                                        sys.stdout.write(json_buf)
                                        sys.stdout.flush()
                                    else:
                                        if text_started:
                                            print()
                                            text_started = False
                                        _spinner.start()   # spin while running next tool
                                    json_buf, in_json = "", False

                    if data.get("done"):
                        break

        except requests.exceptions.ConnectionError:
            _spinner.stop()
            console.print("\n[red]Cannot reach Ollama — is it running?[/]")
        except KeyboardInterrupt:
            _spinner.stop()
            raise
        except Exception as e:
            _spinner.stop()
            console.print(f"\n[red]Stream error: {e}[/]")
        finally:
            _spinner.stop()

        if json_buf:
            start_text()
            sys.stdout.write(json_buf)
            sys.stdout.flush()
        if text_started:
            print()

        return full, tool_results

    def _try_tool(self, json_buf: str, tool_results: list, text_started: bool) -> bool:
        try:
            obj = json.loads(json_buf)
        except json.JSONDecodeError:
            return False
        name = obj.get("name")
        args = obj.get("arguments", {})
        if not name or name not in TOOL_FN_MAP:
            return False
        if text_started:
            print()

        # ── Approval gate ────────────────────────────────────────────────────
        if self._needs_approval(name, args):
            approved = self._request_approval(name, args)
            if not approved:
                # Tell the model it was denied so it can continue gracefully
                tool_results.append((name, f"DENIED by user — do not attempt '{name}' again this turn."))
                return True   # return True so the loop sees a "tool result"

        self._print_tool_call(name, args)
        result = self._execute_tool(name, args)
        self._print_tool_result(name, result)
        tool_results.append((name, result))
        return True

    def _execute_tool(self, name: str, args) -> str:
        fn = TOOL_FN_MAP.get(name)
        if not fn:
            return f"Unknown tool: {name}"
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        try:
            return fn(**args) or "(no output)"
        except Exception as e:
            return f"Tool error ({name}): {e}"

    def _print_tool_call(self, name: str, args: dict):
        # Build a mini-table showing the tool name + args
        t = Table(box=box.MINIMAL, show_header=False, padding=(0, 1),
                  border_style="dim cyan")
        t.add_column("k", style="bold cyan", no_wrap=True)
        t.add_column("v", style="white")
        for k, v in args.items():
            v_str = str(v)
            if len(v_str) > 120:
                v_str = v_str[:117] + "…"
            # highlight file paths, commands
            if k in ("command", "path", "files", "url"):
                t.add_row(k, f"[yellow]{v_str}[/]")
            elif k in ("content", "function_code"):
                lines = v_str.count("\n")
                t.add_row(k, f"[dim]<{lines+1} lines>[/]")
            else:
                t.add_row(k, v_str)
        console.print(f"\n[bold cyan]  ⚙ {name}[/]", end=" ")
        if args:
            console.print(t)
        else:
            console.print()

    def _print_tool_result(self, name: str, result: str):
        preview = result[:2000] + ("…" if len(result) > 2000 else "")
        code_tools  = {"read_file", "run_shell", "run_aider", "run_tests",
                       "lint_and_fix", "web_scrape", "deep_research"}
        git_tools   = {"git_status", "git_diff", "git_log", "git_commit"}
        panel_tools = {"search_web", "list_files", "read_directory",
                       "project_scaffold", "install_package", "docker_run",
                       "list_tools", "get_own_source"}

        is_code = any(kw in result for kw in
                      ["def ", "import ", "class ", "#!/", "fn ", "func ", "const ", "let "])

        if name in code_tools and is_code:
            lang = "python" if ("def " in result or "import " in result) else "bash"
            console.print(Syntax(preview, lang, theme="monokai",
                                 background_color="default", line_numbers=False))
        elif name in git_tools:
            console.print(Panel(preview, border_style="dim yellow",
                                title=f"[dim yellow]{name}[/]", padding=(0, 1)))
        elif name in code_tools | panel_tools:
            console.print(Panel(preview, border_style="dim cyan",
                                title=f"[dim cyan]{name}[/]", padding=(0, 1)))
        elif name in ("remember", "recall", "semantic_recall"):
            console.print(Panel(preview, border_style="dim magenta",
                                title="[dim magenta]memory[/]", padding=(0, 1)))
        elif result.startswith("Tool '") and "added" in result:
            console.print(f"[bold green]  → {preview}[/]")
        else:
            console.print(f"[dim green]  → {preview}[/]")

    # ── Action enforcement (no lying) ─────────────────────────────────────────

    def _enforce_promised_actions(self, content: str, tool_results: list) -> None:
        """If model described an action without actually calling the tool, enforce it."""
        called = {name for name, _ in tool_results}
        c = content.lower()
        # Restart enforcement: model said it's restarting but didn't call restart_self
        restart_phrases = ("restarting omniai", "restart complete", "i will restart",
                           "restarting now", "i am restarting", "going to restart")
        if any(p in c for p in restart_phrases) and "restart_self" not in called:
            console.print("[bold yellow]⚠ Model described a restart without calling restart_self(). Enforcing.[/]")
            restart_self()

    # ── Chat ──────────────────────────────────────────────────────────────────

    def chat(self, user_input: str, images: list = None) -> None:
        msg: dict = {"role": "user", "content": user_input}
        if images:
            msg["images"] = images
        self.history.append(msg)
        self._maybe_compact()

        while True:
            content, tool_results = self._stream_response()
            self.history.append({"role": "assistant", "content": content})
            # ── Enforce: if model SAID restart but didn't call it, do it ─────
            self._enforce_promised_actions(content, tool_results)
            if not tool_results:
                break
            combined = "\n\n".join(f"[{n} result]:\n{r}" for n, r in tool_results)
            self.history.append({
                "role": "user",
                "content": f"Tool results:\n{combined}\n\nContinue or summarise.",
            })

    # ── Loop mode (autonomous project building) ────────────────────────────────

    def loop(self, task: str, max_iterations: int = 30) -> None:
        console.print(Panel(
            f"[bold cyan]Loop Mode — Autonomous[/]\n[dim]{task}[/]\n"
            f"[dim]Max iterations: {max_iterations}  |  Ctrl+C to interrupt[/]",
            style="cyan",
        ))
        loop_suffix = (
            f"\n\nAUTONOMOUS TASK: {task}\n"
            "Work step by step until this task is completely done. "
            "Use tools to build, test, and fix everything. "
            "When the task is 100%% complete, output exactly: TASK_COMPLETE"
        )
        self.history[0]["content"] += loop_suffix

        idle = 0
        for i in range(max_iterations):
            console.print(f"\n[dim cyan]── iteration {i+1}/{max_iterations} ──[/]")
            content, tool_results = self._stream_response()
            self.history.append({"role": "assistant", "content": content})

            if "TASK_COMPLETE" in content:
                console.print("\n[bold green]✓ Task complete![/]")
                return

            if tool_results:
                idle = 0
                combined = "\n\n".join(f"[{n} result]:\n{r}" for n, r in tool_results)
                self.history.append({
                    "role": "user",
                    "content": f"Tool results:\n{combined}\n\nContinue. Output TASK_COMPLETE when fully done.",
                })
            else:
                idle += 1
                if idle >= 2:
                    console.print("\n[yellow]No tool calls for 2 iterations — assuming done.[/]")
                    return
                self.history.append({
                    "role": "user",
                    "content": "Continue working. Use tools to make progress. Output TASK_COMPLETE when done.",
                })
        console.print(f"\n[yellow]Reached max iterations ({max_iterations}).[/]")

    # ── Slash commands ─────────────────────────────────────────────────────────

    def _handle_slash(self, cmd: str) -> bool:
        parts = cmd.strip().split(None, 2)
        name  = parts[0].lower()

        if name == "/help":
            self._show_help()
        elif name == "/model":
            if len(parts) > 1:
                m = MODEL_SHORTCUTS.get(parts[1], parts[1])
                self.model = m
                console.print(f"[green]Model → {self.model}[/]")
            else:
                console.print(f"[cyan]Model: {self.model}[/]  /model coder|reason|vision|big|<name>")
        elif name == "/models":
            self._list_models()
        elif name == "/clear":
            self._init_history()
            console.print("[dim]History cleared.[/]")
        elif name == "/compact":
            self._compact()
        elif name == "/save":
            self._save_session(parts[1] if len(parts) > 1 else "default")
        elif name == "/load":
            self._load_session(parts[1] if len(parts) > 1 else "default")
        elif name == "/sessions":
            self._list_sessions()
        elif name == "/image":
            if len(parts) < 2:
                console.print("[red]Usage: /image <path> [prompt][/]")
            else:
                prompt = parts[2] if len(parts) > 2 else "Describe everything in this image in detail."
                self._send_image(parts[1], prompt)
        elif name == "/cd":
            if len(parts) < 2:
                console.print(f"[cyan]{pathlib.Path.cwd()}[/]")
            else:
                try:
                    os.chdir(os.path.expanduser(parts[1]))
                    self._init_history()
                    console.print(f"[green]→ {pathlib.Path.cwd()}[/]")
                except Exception as e:
                    console.print(f"[red]{e}[/]")
        elif name == "/cwd":
            console.print(f"[cyan]{pathlib.Path.cwd()}[/]")
        elif name == "/loop":
            task = " ".join(parts[1:]) if len(parts) > 1 else console.input("[cyan]Task: [/]").strip()
            self.loop(task)
        elif name == "/mode":
            modes = {"auto": "no confirmations", "cautious": "ask for big changes (default)", "paranoid": "ask for almost everything"}
            if len(parts) > 1 and parts[1] in modes:
                self.approval_mode = parts[1]
                console.print(f"[green]Approval mode → [bold]{self.approval_mode}[/] ({modes[self.approval_mode]})[/]")
            else:
                console.print(f"[cyan]Approval mode: [bold]{self.approval_mode}[/]  ({modes.get(self.approval_mode, '?')})")
                console.print("[dim]  /mode auto      — no confirmations[/]")
                console.print("[dim]  /mode cautious  — ask for big changes (default)[/]")
                console.print("[dim]  /mode paranoid  — ask for everything[/]")
        elif name == "/evolve":
            sub = parts[1].lower() if len(parts) > 1 else ""
            if sub == "stop":
                _clear_evolve_state()
                console.print("[yellow]Evolution mode stopped.[/]")
            elif sub == "status":
                self._show_evolve_status()
            elif sub in ("resume", "continue"):
                self.evolve()
            else:
                goal = " ".join(parts[1:]) if len(parts) > 1 else ""
                self.evolve(goal)
        else:
            return False
        return True

    def _show_help(self):
        console.print(Panel(
            "[bold cyan]Models[/]\n"
            "  /model coder|reason|vision|chat|big|<name>   switch LLM\n"
            "  /models                                        list all\n\n"
            "[bold cyan]Session[/]\n"
            "  /clear   /compact   /save [n]   /load [n]   /sessions\n\n"
            "[bold cyan]Vision[/]\n"
            "  /image <path> [prompt]    send screenshot to vision model\n\n"
            "[bold cyan]Navigation[/]\n"
            "  /cd <path>    change dir + reload .omni.md\n"
            "  /cwd          show current dir\n\n"
            "[bold cyan]Autonomous[/]\n"
            "  /loop <task>          run autonomously until TASK_COMPLETE\n"
            "  /evolve [goal]        self-improvement loop (builds new tools)\n"
            "  /evolve resume        resume after Ctrl+C pause\n"
            "  /evolve status        show evolution history\n"
            "  /evolve stop          exit evolution mode\n\n"
            "[bold cyan]Project file[/]\n"
            "  Create .omni.md in any directory — auto-loaded as context\n\n"
            "[bold cyan]Control[/]\n"
            "  Ctrl+C   interrupt current action (pause evolve, stop chat)\n"
            "  rollback_self()       undo last self_improve (say 'rollback')",
            title="[bold cyan]OmniAI Help[/]", border_style="cyan",
        ))

    def _list_models(self):
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            for m in [x["name"] for x in r.json().get("models", [])]:
                console.print(f"  {m}{' [cyan]◀[/]' if m == self.model else ''}")
        except Exception:
            console.print("[red]Cannot reach Ollama.[/]")

    def _save_session(self, name: str):
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        p = SESSIONS_DIR / f"{name}.json"
        p.write_text(json.dumps({"model": self.model, "history": self.history}, indent=2))
        console.print(f"[green]Saved '{name}' ({len(self.history)} messages)[/]")

    def _load_session(self, name: str):
        p = SESSIONS_DIR / f"{name}.json"
        if not p.exists():
            console.print(f"[red]No session '{name}'[/]")
            return
        d = json.loads(p.read_text())
        self.model, self.history = d.get("model", MODEL_DEFAULT), d.get("history", [])
        console.print(f"[green]Loaded '{name}' ({len(self.history)} msgs, {self.model})[/]")

    def _list_sessions(self):
        ss = sorted(SESSIONS_DIR.glob("*.json"))
        [console.print(f"  [cyan]{s.stem}[/] ({s.stat().st_size//1024}KB)") for s in ss] or \
        console.print("[dim]No sessions.[/]")

    def _send_image(self, image_path: str, prompt: str):
        p = pathlib.Path(image_path).expanduser()
        if not p.exists():
            console.print(f"[red]Not found: {image_path}[/]")
            return
        img_b64 = base64.b64encode(p.read_bytes()).decode()
        old = self.model
        self.model = MODEL_VISION
        console.print(f"[dim cyan]Vision: {MODEL_VISION}[/]")
        self.chat(prompt, images=[img_b64])
        self.model = old

    # ── Evolution loop ─────────────────────────────────────────────────────────

    def evolve(self, goal: str = "", max_cycles: int = 50) -> None:
        """Autonomous self-improvement loop. Persists across restarts via EVOLVE_FILE."""
        # Load or init state
        state = _load_evolve_state()
        if state is None:
            state = {
                "goal":       goal or "Maximise capabilities — add new tools, fix weak ones, expand integrations",
                "cycle":      0,
                "max_cycles": max_cycles,
                "completed":  [],
                "started":    datetime.datetime.now().isoformat(),
            }
        else:
            console.print(f"\n[bold cyan]Resuming evolution[/] [dim](cycle {state['cycle']}/{state['max_cycles']})[/]")

        _save_evolve_state(state)

        # Build suggested areas excluding already-completed ones
        done_lower = [c.lower() for c in state["completed"]]
        suggestions = [s for s in _EVOLVE_SUGGESTIONS
                       if not any(kw in s.lower() for kw in done_lower[:3])][:8]

        EVOLVE_PROMPT = (
            f"\n\n{'━'*60}\n"
            f"EVOLUTION MODE ACTIVE\n"
            f"Goal: {state['goal']}\n"
            f"Cycle: {state['cycle'] + 1}/{state['max_cycles']}\n"
            f"Already done: {json.dumps(state['completed']) if state['completed'] else 'nothing yet'}\n\n"
            "YOUR JOB THIS CYCLE:\n"
            "1. run_self_test() — verify healthy before starting\n"
            "2. list_tools() — see current capabilities\n"
            "3. Pick ONE improvement NOT in the 'already done' list above\n"
            "4. deep_research() or web_scrape() to get real implementation details\n"
            "5. backup_self() — ALWAYS before any change\n"
            "6. self_improve() for new tools  OR  edit_file() for fixing existing ones\n"
            "7. run_self_test() — verify markers intact after change\n"
            "8. If test PASSES and new tool added: restart_self() to activate\n"
            "9. If test FAILS: rollback_self() immediately, try different approach\n"
            "10. Output exactly: EVOLUTION_COMPLETE: <one line describing what you did>\n\n"
            f"SUGGESTED AREAS (pick one or choose your own):\n"
            + "\n".join(f"  • {s}" for s in suggestions) + "\n"
            f"{'━'*60}\n"
        )

        # Inject into system prompt (first message)
        if "EVOLUTION MODE ACTIVE" not in self.history[0]["content"]:
            self.history[0]["content"] += EVOLVE_PROMPT

        console.print(Panel(
            Text.assemble(
                ("Goal  ", "dim"), (state["goal"] + "\n", "white"),
                ("Done  ", "dim"), (f"{len(state['completed'])} improvements  ·  ", "green"),
                ("Cycle ", "dim"), (f"{state['cycle']}/{state['max_cycles']}\n", "cyan"),
                ("\nCtrl+C → pause and talk  ·  ", "dim"),
                ("/evolve stop", "cyan"), (" → exit evolution mode\n", "dim"),
                ("/evolve status", "cyan"), (" → show what was built\n", "dim"),
            ),
            title="[bold cyan]⚙ Evolution Mode[/]",
            border_style="cyan", box=box.ROUNDED,
        ))

        while state["cycle"] < state["max_cycles"]:
            state["cycle"] += 1
            _save_evolve_state(state)

            console.print(f"\n[dim cyan]{'─'*50}[/]")
            console.print(f"[bold cyan]⚙ Evolution cycle {state['cycle']}/{state['max_cycles']}[/]"
                          f"  [dim]{len(state['completed'])} improvements so far[/]")

            self.history.append({"role": "user", "content": (
                f"Evolution cycle {state['cycle']}. "
                f"Completed so far: {json.dumps(state['completed']) if state['completed'] else 'none yet'}.\n\n"
                "Step 1: Run run_self_test() and list_tools() to audit current state.\n"
                "Step 2: Output your PLAN as plain text (what you will add/improve and why) "
                "BEFORE calling any write/modify tools. Start with 'PLAN:'\n"
                "Step 3: Wait — the user will review your plan. If they say go ahead, proceed.\n"
                "Step 4: backup_self(), implement, run_self_test(), restart if needed.\n"
                "Step 5: End with: EVOLUTION_COMPLETE: <one-line description>"
            )})
            self._maybe_compact()

            idle = 0
            cycle_done = False
            while not cycle_done:
                try:
                    content, tool_results = self._stream_response()
                except KeyboardInterrupt:
                    _spinner.stop()
                    console.print("\n\n[bold yellow]Evolution paused.[/]")
                    console.print("[dim]Type normally to chat. Then:[/]")
                    console.print("  [cyan]/evolve resume[/]  — continue evolving")
                    console.print("  [cyan]/evolve stop[/]    — exit evolution mode")
                    _save_evolve_state(state)
                    return

                self.history.append({"role": "assistant", "content": content})
                self._enforce_promised_actions(content, tool_results)

                # ── Plan review ──────────────────────────────────────────────
                if self._evolve_plan_mode and "PLAN:" in content and not tool_results:
                    plan_text = content.split("PLAN:", 1)[-1].strip()[:600]
                    console.print()
                    console.print(Panel(
                        Text.from_markup(
                            f"[white]{plan_text}[/]\n\n"
                            "  [dim][[/][bold green]y[/][dim]] go ahead   "
                            "[[/][bold red]n[/][dim]] skip this cycle   "
                            "[[/][bold yellow]m[/][dim]] modify (type new instruction)[/]"
                        ),
                        title="[bold cyan]⚙ OmniAI's Plan for this cycle[/]",
                        border_style="cyan", box=box.ROUNDED,
                    ))
                    try:
                        answer = input("  → ").strip()
                    except (EOFError, KeyboardInterrupt):
                        answer = "n"

                    if answer.lower() in ("n", "no", "skip"):
                        console.print("[yellow]Skipping this cycle.[/]")
                        self.history.append({"role": "user", "content":
                            "User skipped this plan. Choose a different improvement for the next cycle."})
                        cycle_done = True
                        continue
                    elif answer.lower() not in ("y", "yes", ""):
                        # User provided modification instructions
                        self.history.append({"role": "user", "content":
                            f"User feedback on your plan: {answer}\n"
                            "Adjust your approach accordingly, then proceed with the modified plan."})
                        continue
                    else:
                        self.history.append({"role": "user", "content":
                            "Plan approved. Proceed: backup_self(), implement, test, restart if needed. "
                            "End with EVOLUTION_COMPLETE: <description>"})
                        continue

                if "EVOLUTION_COMPLETE" in content:
                    # Extract description after the marker
                    desc = content.split("EVOLUTION_COMPLETE", 1)[-1]
                    desc = desc.lstrip(": ").split("\n")[0].strip()[:120]
                    if not desc:
                        desc = f"cycle {state['cycle']} improvement"
                    state["completed"].append(desc)
                    _save_evolve_state(state)
                    _log_evolution({"cycle": state["cycle"], "improvement": desc, "model": self.model})
                    console.print(f"\n[bold green]✓ {desc}[/]")
                    cycle_done = True

                elif tool_results:
                    idle = 0
                    combined = "\n\n".join(f"[{n}]:\n{r}" for n, r in tool_results)
                    self.history.append({"role": "user", "content":
                        f"Tool results:\n{combined}\n\n"
                        "Continue. End with EVOLUTION_COMPLETE: <description> when done."
                    })
                else:
                    idle += 1
                    if idle >= 3:
                        console.print("\n[yellow]No progress this cycle — skipping.[/]")
                        cycle_done = True
                    else:
                        self.history.append({"role": "user", "content":
                            "Continue implementing the improvement. Use tools. "
                            "End with EVOLUTION_COMPLETE: <description> when done."
                        })

        _clear_evolve_state()
        console.print(Panel(
            f"[bold green]Evolution complete![/]\n"
            f"[dim]{len(state['completed'])} improvements made over {state['cycle']} cycles.[/]\n\n"
            + "\n".join(f"  [green]✓[/] {c}" for c in state["completed"]),
            title="[bold green]⚙ Evolution Summary[/]", border_style="green",
        ))

    def _show_evolve_status(self) -> None:
        """Show evolution log — what has been built."""
        state = _load_evolve_state()
        try:
            log: list = json.loads(EVOLVE_LOG.read_text()) if EVOLVE_LOG.exists() else []
        except Exception:
            log = []

        t = Table(box=box.MINIMAL_DOUBLE_HEAD, border_style="cyan",
                  show_header=True, padding=(0, 1))
        t.add_column("#",    style="dim", width=3)
        t.add_column("Cycle", style="cyan", width=6)
        t.add_column("Improvement", style="white")
        t.add_column("When", style="dim", width=20)

        for i, entry in enumerate(log[-20:], 1):
            ts = entry.get("timestamp", "")[:16].replace("T", " ")
            t.add_row(str(i), str(entry.get("cycle", "?")),
                      entry.get("improvement", "?"), ts)

        if log:
            console.print(t)
        else:
            console.print("[dim]No evolution history yet.[/]")

        if state:
            console.print(f"\n[cyan]Evolution active[/] — cycle {state['cycle']}/{state['max_cycles']}")
            console.print(f"[dim]/evolve resume  to continue  ·  /evolve stop  to exit[/]")

    # ── REPL ──────────────────────────────────────────────────────────────────

    def _recent_activity(self) -> list[str]:
        """Return last 3 memory entries as activity lines."""
        try:
            if not MEMORY_FILE.exists():
                return []
            mems = json.loads(MEMORY_FILE.read_text())
            recent = list(mems.items())[-3:]
            return [f"[dim]remembered:[/] [white]{v['value'][:55]}{'…' if len(v['value'])>55 else ''}[/]"
                    for _, v in reversed(recent)]
        except Exception:
            return []

    def run(self):
        from rich.columns import Columns

        n_tools   = len(TOOL_FN_MAP)
        mem_count = 0
        try:
            if MEMORY_FILE.exists():
                mem_count = len(json.loads(MEMORY_FILE.read_text()))
        except Exception:
            pass

        cwd   = str(pathlib.Path.cwd()).replace(str(pathlib.Path.home()), "~")
        model = self.model

        # ── Left panel: identity ──────────────────────────────────────────────
        MACK3Y = Text.assemble(
            ("      ╭─────────╮\n",    "cyan"),
            ("    ╭─┤", "cyan"), (" ◼  ◼  ", "white"), ("├─╮\n", "cyan"),
            ("    │ ╰── ", "cyan"), ("˅˅˅", "dim white"), (" ──╯ │\n", "cyan"),
            ("    ╰─────────────╯\n",  "cyan"),
            ("  ╭───────────────╮\n",  "dim cyan"),
            ("  │  ▓▓▓▓▓▓▓▓▓▓  │\n",  "dim cyan"),
            ("  │ ▓▓▓▓▓▓▓▓▓▓▓▓ │\n",  "dim cyan"),
            ("  ╰───────────────╯\n",  "dim cyan"),
        )

        short_model = model if len(model) <= 22 else model[:19] + "…"

        left = Text.assemble(
            ("\n  Welcome back, ", "dim"),
            ("mack3y", "bold cyan"),
            ("!\n\n", "dim"),
        )
        left.append_text(MACK3Y)
        left.append("\n")
        left.append(f"  {short_model}\n", style="bold cyan")
        mode_clr = {"auto": "dim", "cautious": "green", "paranoid": "yellow"}.get(self.approval_mode, "dim")
        left.append(f"  {n_tools} tools  ·  {mem_count} memories  ·  ", style="dim")
        left.append(f"mode:{self.approval_mode}\n", style=mode_clr)
        left.append(f"  {cwd}\n", style="dim white")

        left_panel = Panel(left, border_style="cyan", box=box.ROUNDED,
                           padding=(0, 1), width=38)

        # ── Right panel: tips + activity ──────────────────────────────────────
        tips = Text.assemble(
            ("Quick start\n", "bold cyan"),
            ("─" * 38 + "\n", "dim cyan"),
            ("/model chat", "cyan"),   ("  · more conversational\n",  "dim"),
            ("/model reason", "cyan"), ("  · deep reasoning\n",       "dim"),
            ("/loop ", "cyan"),        ("<task>  · autonomous build\n","dim"),
            ("/evolve", "bold cyan"),  ("  · self-improvement loop\n", "dim"),
            ("/image ", "cyan"),       ("<path>  · analyze image\n",  "dim"),
            (".omni.md", "cyan"),      ("  · project context file\n", "dim"),
            ("\n"),
            ("Recent memories\n", "bold cyan"),
            ("─" * 38 + "\n", "dim cyan"),
        )
        activity = self._recent_activity()
        if activity:
            for line in activity:
                tips.append_text(Text.from_markup(f"  {line}\n"))
        else:
            tips.append("  No memories yet — ask me to remember something\n", style="dim")

        right_panel = Panel(tips, border_style="cyan", box=box.ROUNDED,
                            padding=(0, 1))

        console.print(Columns([left_panel, right_panel], padding=(0, 1)),
                      justify="left")
        console.print()

        while True:
            try:
                user_input = console.input("\n[bold cyan]you ›[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Bye.[/]")
                break
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "bye"):
                console.print("[dim]Bye.[/]")
                break
            if user_input.startswith("/"):
                if not self._handle_slash(user_input):
                    console.print("[red]Unknown command — /help[/]")
                continue
            try:
                self.chat(user_input)
            except KeyboardInterrupt:
                _spinner.stop()
                console.print("\n[yellow]Interrupted — Ctrl+C again to quit.[/]")
            except Exception as e:
                _spinner.stop()
                console.print(f"\n[red]Error: {e}[/]")


# ── Entry point ────────────────────────────────────────────────────────────────

def _exit_handler(*_):
    _spinner.stop()
    sys.exit(0)

if __name__ == "__main__":
    # Clean exit when terminal closes (Konsole/tmux HUP) — no "process still running" dialog
    signal.signal(signal.SIGHUP,  _exit_handler)
    signal.signal(signal.SIGTERM, _exit_handler)

    agent = OmniAI()
    args  = sys.argv[1:]

    if "--loop" in args:
        args.remove("--loop")
        task = " ".join(args) if args else console.input("[bold cyan]Autonomous task: [/]").strip()
        agent.loop(task)
    elif "--evolve" in args:
        args.remove("--evolve")
        agent.run()   # show banner first
        agent.evolve(" ".join(args))
    elif args:
        agent.chat(" ".join(args))
    else:
        agent.run()
        # Auto-resume evolution if it was running when we restarted
        evolve_state = _load_evolve_state()
        if evolve_state:
            console.print(f"\n[bold cyan]⚙ Evolution mode was active — resuming…[/]")
            agent.evolve()
