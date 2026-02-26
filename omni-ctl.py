#!/home/mack3y/interpreter-venv/bin/python3
"""OmniAI Control Panel — manage all local AI services from one place."""

import subprocess, sys, os, time, webbrowser, signal, threading
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich import box

console = Console()

SERVICES = [
    ("omni-pipelines",      "Pipelines",      "http://localhost:9099"),
    ("perplexica-frontend", "AI Web Search",  "http://localhost:3000"),
    ("searxng",             "Search Engine",  "http://localhost:8080"),
    ("n8n",                 "Automation",     "http://localhost:5678"),
    ("chroma",              "Vector DB",      "http://localhost:8000"),
]
COMFYUI_URL = "http://localhost:8188"
OLLAMA_URL  = "http://localhost:11434"


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd, capture=True):
    r = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
    return r.stdout.strip() if capture else r.returncode

def docker_status(name):
    out = run(f"docker inspect --format '{{{{.State.Status}}}}' {name} 2>/dev/null")
    return out or "stopped"

def ollama_running():
    return run("curl -s --max-time 1 http://localhost:11434/api/tags") != ""

def comfyui_running():
    return run("curl -s --max-time 1 http://localhost:8188/system_stats") != ""

def ollama_models():
    import json
    raw = run("curl -s http://localhost:11434/api/tags")
    try:
        return [m["name"] for m in json.loads(raw)["models"]]
    except Exception:
        return []

def vram_usage():
    out = run("nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null")
    if out:
        used, total = out.split(", ")
        return f"{int(used)//1024:.1f}/{int(total)//1024:.1f} GB"
    return "N/A"


# ── Status table ──────────────────────────────────────────────────────────────

def status_table():
    t = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan",
              title="[bold cyan]OmniAI Services[/]")
    t.add_column("Service",    style="bold white", min_width=20)
    t.add_column("Status",     min_width=10)
    t.add_column("URL",        style="dim")

    # Docker services
    for name, label, url in SERVICES:
        s = docker_status(name)
        dot = "[green]● running[/]" if s == "running" else f"[red]● {s}[/]"
        t.add_row(label, dot, url)

    # Ollama
    ok = ollama_running()
    models = ollama_models() if ok else []
    dot = "[green]● running[/]" if ok else "[red]● stopped[/]"
    t.add_row("Ollama", dot, f"{len(models)} models loaded" if ok else OLLAMA_URL)

    # ComfyUI
    ok = comfyui_running()
    dot = "[green]● running[/]" if ok else "[red]● stopped[/]"
    t.add_row("ComfyUI", dot, COMFYUI_URL)

    return t


def model_table():
    models = ollama_models()
    if not models:
        return Panel("[dim]Ollama not running[/]", title="Models")
    t = Table(box=box.SIMPLE, show_header=False)
    t.add_column("Model", style="cyan")
    for m in models:
        t.add_row(m)
    return Panel(t, title="[bold cyan]Loaded Models[/]")


def gpu_panel():
    vram = vram_usage()
    out = run("nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu --format=csv,noheader 2>/dev/null")
    name, temp, util = ("Unknown", "?", "?") if not out else [x.strip() for x in out.split(",")]
    return Panel(
        f"[bold white]{name}[/]\n"
        f"VRAM: [cyan]{vram}[/]  Temp: [yellow]{temp}°C[/]  Load: [green]{util}[/]",
        title="[bold cyan]GPU[/]"
    )


# ── Actions ───────────────────────────────────────────────────────────────────

def start_all_docker():
    console.print("[yellow]Starting Docker stack...[/]")
    run(f"cd {os.path.expanduser('~/omni-stack')} && docker compose up -d", capture=False)

def stop_all_docker():
    console.print("[yellow]Stopping Docker stack...[/]")
    run(f"cd {os.path.expanduser('~/omni-stack')} && docker compose down", capture=False)

def open_browser(url):
    webbrowser.open(url)

def launch_aider(path=None):
    path = path or os.path.expanduser("~")
    cmd = (f"konsole --new-tab -e bash -c '"
           f"source ~/aider-venv/bin/activate && "
           f"cd {path} && "
           f"aider --model ollama/qwen2.5-coder:14b; exec bash'")
    subprocess.Popen(cmd, shell=True)
    console.print(f"[green]Launched Aider in {path}[/]")

def launch_voice():
    cmd = ("konsole --new-tab -e bash -c '"
           "source ~/ai-audio-venv/bin/activate && "
           "python ~/omni-stack/voice-to-aider.py; exec bash'")
    subprocess.Popen(cmd, shell=True)
    console.print("[green]Voice pipeline launched — hold Super+` to speak[/]")

def launch_aichat():
    cmd = ("konsole --new-tab -e bash -c '"
           "source ~/ai-audio-venv/bin/activate && "
           "aichat; exec bash'")
    subprocess.Popen(cmd, shell=True)

def launch_omni_ai():
    cmd = ("konsole --new-tab -e /home/mack3y/interpreter-venv/bin/python3 "
           "/home/mack3y/omni-stack/omni-ai.py")
    subprocess.Popen(cmd, shell=True)
    console.print("[green]OmniAI Agent launched in new tab[/]")

def pull_model():
    name = console.input("[cyan]Model name to pull (e.g. llava:13b): [/]").strip()
    if name:
        console.print(f"[yellow]Pulling {name}...[/]")
        subprocess.run(f"ollama pull {name}", shell=True)


# ── Main menu ─────────────────────────────────────────────────────────────────

MENU = [
    ("1", "Start all Docker services",    start_all_docker),
    ("2", "Stop all Docker services",     stop_all_docker),
    ("3", "Open Pipelines API",           lambda: open_browser("http://localhost:9099")),
    ("4", "Open Perplexica (Web Search)", lambda: open_browser("http://localhost:3000")),
    ("5", "Open ComfyUI (Image Gen)",     lambda: open_browser("http://localhost:8188")),
    ("6", "Open n8n (Automation)",        lambda: open_browser("http://localhost:5678")),
    ("7", "Launch Aider (AI Coding)",     lambda: launch_aider()),
    ("8", "Launch Voice Pipeline",        launch_voice),
    ("9", "Pull a new Ollama model",      pull_model),
    ("a", "Launch OmniAI Agent",         launch_omni_ai),
    ("r", "Refresh status",              None),
    ("q", "Quit",                         None),
]

def draw():
    console.clear()
    console.print(Panel("[bold cyan]OmniAI Control Panel[/]  [dim]RTX 5070 Ti • Local AI Stack[/]",
                        style="cyan"))
    console.print(Columns([status_table(), model_table(), gpu_panel()], equal=False, expand=True))
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column("Key",   style="bold cyan", min_width=4)
    t.add_column("Action", style="white")
    for key, label, _ in MENU:
        t.add_row(f"[{key}]", label)
    console.print(t)

def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    if not sys.stdin.isatty():
        draw()
        return
    while True:
        draw()
        try:
            choice = console.input("\n[bold cyan]> [/]").strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye.[/]")
            sys.exit(0)
        for key, _, fn in MENU:
            if choice == key:
                if fn:
                    fn()
                    if fn not in (start_all_docker, stop_all_docker, pull_model):
                        time.sleep(0.5)
                break
        if choice == "q":
            console.print("[dim]Bye.[/]")
            sys.exit(0)

if __name__ == "__main__":
    main()
