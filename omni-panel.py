#!~/interpreter-venv/bin/python3
"""OmniAI — autonomous vibecoder home base."""

import os, sys, re, queue, select, signal, subprocess, threading, time, tempfile
import requests

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static, TextArea
from textual import on
from rich.text import Text


def _clipboard_copy(text: str) -> bool:
    """Copy text to system clipboard. Tries xclip → xsel → wl-copy."""
    for cmd in (
        ["xclip", "-selection", "clipboard"],
        ["xsel",  "--clipboard", "--input"],
        ["wl-copy"],
    ):
        try:
            subprocess.run(cmd, input=text.encode(), check=True,
                           capture_output=True)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False

# ── Config ─────────────────────────────────────────────────────────────────────

PYTHON      = "~/interpreter-venv/bin/python3"
VOICE_PY    = "~/ai-audio-venv/bin/python3"
OMNI_AI     = "~/omni-stack/omni-ai.py"
OLLAMA_URL  = "http://localhost:11434"
COMFYUI_URL = "http://localhost:8188"

SERVICES = [
    ("omni-pipelines",      "Pipelines"),
    ("perplexica-frontend", "Web Search"),
    ("searxng",             "SearXNG"),
    ("n8n",                 "n8n"),
    ("chroma",              "ChromaDB"),
]

HISTORY_MAX  = 500
ANSI_RE      = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
# Spinner frame chars — stale lines starting with these are suppressed
SPINNER_CHARS = frozenset("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏◆◇◈◉◎○◌◍◐◑◒◓*✦✸✺")

# ── Helpers ────────────────────────────────────────────────────────────────────

def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def docker_status(name: str) -> str:
    r = subprocess.run(
        f"docker inspect --format '{{{{.State.Status}}}}' {name} 2>/dev/null",
        shell=True, capture_output=True, text=True,
    )
    return r.stdout.strip() or "stopped"


def gpu_info() -> str:
    r = subprocess.run(
        "nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,"
        "memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null",
        shell=True, capture_output=True, text=True,
    )
    if r.stdout.strip():
        parts = [x.strip() for x in r.stdout.strip().split(",")]
        if len(parts) >= 4:
            temp, util, used, total = parts[:4]
            try:
                util_n   = int(util.replace("%","").strip())
                used_gb  = int(used) // 1024
                total_gb = int(total) // 1024
                filled   = round(10 * util_n / 100)
                bar      = "█" * filled + "░" * (10 - filled)
                return f"{temp}°C [{bar}] {util_n}%  {used_gb}/{total_gb}GB"
            except (ValueError, TypeError):
                pass
    return "N/A"


def ollama_running() -> bool:
    try:
        requests.get(f"{OLLAMA_URL}/api/tags", timeout=1)
        return True
    except Exception:
        return False


def comfyui_running() -> bool:
    try:
        requests.get(f"{COMFYUI_URL}/system_stats", timeout=1)
        return True
    except Exception:
        return False


def ollama_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def colorize_line(line: str) -> Text:
    t = Text(line)
    s = line.strip()
    if s.startswith("you › "):
        t.stylize("bold white", 0, 6)
        t.stylize("bright_white", 6)
    elif s.startswith("ai › "):
        t.stylize("bold bright_cyan", 0, 5)
        t.stylize("white", 5)
    elif "⚙" in s:
        t.stylize("dim cyan")
    elif s.startswith("→") or "  →" in s:
        t.stylize("dim green")
    elif "ERROR" in s or "Error:" in s:
        t.stylize("bold red")
    elif s.startswith("[") and s.endswith("]"):
        t.stylize("yellow")
    elif s.startswith("#"):
        t.stylize("bold magenta")
    elif s.startswith("==="):
        t.stylize("bold cyan")
    return t


def _is_spinner_line(s: str) -> bool:
    """Return True if this looks like a spinner animation frame (suppress it)."""
    stripped = s.strip()
    if not stripped:
        return False
    return stripped[0] in SPINNER_CHARS


# ── Sidebar widgets ────────────────────────────────────────────────────────────

class GPUBar(Static):
    """Live GPU stats bar."""
    gpu_text: reactive[str] = reactive("Loading…")

    def on_mount(self) -> None:
        self.refresh_gpu()
        self.set_interval(3, self.refresh_gpu)

    def refresh_gpu(self) -> None:
        self.gpu_text = gpu_info()

    def watch_gpu_text(self, val: str) -> None:
        t = Text(f" GPU  {val}")
        t.stylize("dim", 0, 5)
        t.stylize("bright_cyan", 5)
        self.update(t)


class RamBar(Static):
    """Live RAM usage bar."""
    ram_text: reactive[str] = reactive("Loading…")

    def on_mount(self) -> None:
        self.refresh_ram()
        self.set_interval(5, self.refresh_ram)

    def refresh_ram(self) -> None:
        try:
            with open("/proc/meminfo") as f:
                raw = f.read()
            info: dict[str, int] = {}
            for line in raw.splitlines():
                k, v = line.split(":", 1)
                info[k.strip()] = int(v.strip().split()[0])
            total = info.get("MemTotal", 0)
            avail = info.get("MemAvailable", 0)
            used  = total - avail
            used_gb  = used  / 1024 / 1024
            total_gb = total / 1024 / 1024
            pct    = used / total if total else 0
            filled = round(10 * pct)
            bar    = "█" * filled + "░" * (10 - filled)
            self.ram_text = f"{used_gb:.1f}/{total_gb:.1f}GB [{bar}] {int(pct*100)}%"
        except Exception:
            self.ram_text = "N/A"

    def watch_ram_text(self, val: str) -> None:
        t = Text(f" RAM  {val}")
        t.stylize("dim", 0, 5)
        t.stylize("bright_green", 5)
        self.update(t)


class ServiceRow(Static):
    """One docker service status row."""
    status: reactive[str] = reactive("…")

    def __init__(self, svc_name: str, svc_label: str) -> None:
        super().__init__()
        self.svc_name  = svc_name
        self.svc_label = svc_label

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(10, self._refresh)

    def _refresh(self) -> None:
        self.status = docker_status(self.svc_name)

    def watch_status(self, val: str) -> None:
        running = val == "running"
        dot     = "●" if running else "○"
        clr     = "bright_green" if running else "red"
        self.update(Text.assemble(
            (" ", ""),
            (dot + " ", clr),
            (f"{self.svc_label:<14}", "white" if running else "dim"),
        ))


class OllamaRow(Static):
    ok: reactive[bool] = reactive(False)

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(10, self._refresh)

    def _refresh(self) -> None:
        self.ok = ollama_running()

    def watch_ok(self, val: bool) -> None:
        dot, clr = ("●", "bright_green") if val else ("○", "dim")
        self.update(Text.assemble(
            (" ", ""), (dot + " ", clr),
            ("Ollama        ", "white" if val else "dim"),
        ))


class ComfyRow(Static):
    ok: reactive[bool] = reactive(False)

    def on_mount(self) -> None:
        self._refresh()
        self.set_interval(10, self._refresh)

    def _refresh(self) -> None:
        self.ok = comfyui_running()

    def watch_ok(self, val: bool) -> None:
        dot, clr = ("●", "bright_green") if val else ("○", "dim")
        self.update(Text.assemble(
            (" ", ""), (dot + " ", clr),
            ("ComfyUI       ", "white" if val else "dim"),
        ))


class ModeModelBar(Static):
    """Shows the currently active mode and model in plain English."""

    def on_mount(self) -> None:
        self.update_state("Ask Me First", "Best Quality (32b)")

    def update_state(self, mode_label: str, model_label: str) -> None:
        self.update(Text.assemble(
            (" Mode  ", "dim"),
            (mode_label,  "bold bright_cyan"),
            ("\n Model ", "dim"),
            (model_label, "bold bright_cyan"),
        ))


class SidebarBtn(Static):
    """Clickable sidebar action item. Optional desc shows on line 2."""

    def __init__(self, icon: str, label: str, action_id: str, desc: str = "") -> None:
        super().__init__()
        self._icon      = icon
        self._label     = label
        self._action_id = action_id
        self._desc      = desc

    def on_mount(self) -> None:
        parts: list[tuple[str, str]] = [
            (f" {self._icon} ", "cyan"),
            (self._label, "white"),
        ]
        if self._desc:
            parts += [("\n    ", ""), (self._desc, "dim #4a7070")]
        self.update(Text.assemble(*parts))

    def on_click(self) -> None:
        self.app.sidebar_action(self._action_id)  # type: ignore


class StatusBar(Static):
    model_name: reactive[str] = reactive("qwen2.5-coder:32b-instruct-q4_K_M")

    def on_mount(self) -> None:
        self._render()

    def watch_model_name(self, _: str) -> None:
        self._render()

    def _render(self) -> None:
        self.update(Text.assemble(
            ("  ⚙ OmniAI  ", "bold cyan"),
            ("model: ", "dim"),
            (self.model_name, "bright_cyan"),
            ("   ^⏎ send · ^C interrupt · ^V voice · ^Y copy · ^↑↓ history · /help", "dim"),
        ))


# @@INSERT_WIDGET@@


class ActivityBar(Static):
    """Live task-progress line — shows current action + elapsed time.

    Mirrors the Claude Code status line:
      ⟳ Calling run_shell…  (12s)
      ✓ Done  (8s)          ← fades after 3 s
    """

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._start:   float = 0.0   # wall time when user sent message
        self._action:  str   = ""    # most recent tool/action text
        self._active:  bool  = False # True while AI is working
        self._done_at: float = 0.0   # wall time when AI replied

    def on_mount(self) -> None:
        self.set_interval(0.5, self._tick)

    # ── Called by OmniPanel ────────────────────────────────────────────────────

    def start(self) -> None:
        """User sent a message — begin timing."""
        self._start  = time.time()
        self._action = "Thinking"
        self._active = True
        self._done_at = 0.0
        self._render()

    def set_action(self, action: str) -> None:
        """Tool call detected — update action label."""
        if not self._active:
            self._start  = time.time()
            self._active = True
        self._action = action
        self._render()

    def done(self) -> None:
        """AI reply arrived — show Done then fade."""
        self._active  = False
        self._done_at = time.time()
        elapsed = self._done_at - self._start if self._start else 0
        self.update(Text.assemble(
            (" ✓ ", "bold green"),
            ("Done", "bright_white"),
            (f"  ({elapsed:.0f}s)", "dim"),
        ))

    # ── Internal ───────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        if self._active:
            self._render()
        elif self._done_at and (time.time() - self._done_at) > 3.0:
            # Fade out "Done" after 3 s of inactivity
            self.update("")
            self._done_at = 0.0

    def _render(self) -> None:
        elapsed = time.time() - self._start if self._start else 0
        # Braille pulse while active
        frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        frame  = frames[int(time.time() * 8) % len(frames)]
        mins   = int(elapsed) // 60
        secs   = int(elapsed) % 60
        timer  = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        self.update(Text.assemble(
            (f" {frame} ", "bold cyan"),
            (self._action, "bright_white"),
            ("…", "dim cyan"),
            (f"  ({timer})", "dim"),
        ))


# ── Main App ───────────────────────────────────────────────────────────────────

class OmniPanel(App):
    TITLE     = "OmniAI"
    SUB_TITLE = "⚙ autonomous vibecoder ⚙"

    CSS = """
    /* ── $USER space-hacker palette ─────────────────────────────────────── */
    Screen {
        background: #050510;
    }

    Header {
        background: #0a0a1e;
        color: #64dcbc;
        text-style: bold;
        border-bottom: solid #1a3a3a;
    }

    Footer {
        background: #0a0a1e;
        color: #3a6060;
        border-top: solid #1a3a3a;
    }

    #sidebar {
        width: 33;
        min-width: 33;
        background: #07071a;
        border-right: solid #1e3e3e;
        overflow-y: auto;
        overflow-x: hidden;
        padding: 0 0 1 0;
    }

    #main { padding: 0 1; }

    #chat_log {
        height: 1fr;
        border: solid #1a3a3a;
        background: #03030e;
        padding: 0 1;
        scrollbar-color: #2a5a5a;
        scrollbar-background: #07071a;
    }

    #input_row  { height: 6; margin-top: 1; }
    #chat_input {
        width: 1fr;
        background: #07071a;
        border: solid #1e3e3e;
        color: #c0f0e8;
    }
    #chat_input:focus {
        border: solid #64dcbc;
    }
    #chat_input .text-area--cursor {
        background: #64dcbc;
        color: #050510;
    }
    #chat_input .text-area--gutter {
        display: none;
    }
    #voice_btn  { width: 5; min-width: 5; background: #0d1a1a; border: solid #1e3e3e; }
    #send_btn   {
        width: 8; min-width: 8;
        background: #0d2a2a;
        border: solid #2a7a6a;
        color: #64dcbc;
    }
    #send_btn:hover { background: #1a4a4a; }

    StatusBar {
        height: 1;
        background: #0a1a1a;
        border-top: solid #1a3a3a;
    }

    GPUBar { height: 2; padding: 1 0 0 0; }
    RamBar { height: 2; padding: 0 0 0 0; }
    ModeModelBar {
        height: 4;
        padding: 1 0 0 0;
        border-bottom: solid #1e3e3e;
        margin-bottom: 0;
    }

    ServiceRow { height: 1; }
    OllamaRow  { height: 1; }
    ComfyRow   { height: 1; }

    .sec {
        color: #64dcbc;
        text-style: bold;
        height: 2;
        padding: 1 0 0 1;
    }

    SidebarBtn {
        height: 2;
        padding: 0 0 0 0;
        color: #8ab8b0;
        background: transparent;
    }
    SidebarBtn:hover {
        background: #0d2020;
        color: #64dcbc;
    }

    ActivityBar {
        height: 1;
        background: #04041a;
        border-top: dashed #1a2a2a;
        padding: 0 1;
    }

    /* @@INSERT_CSS@@ */
    """

    BINDINGS = [
        Binding("ctrl+enter",  "submit_input",   "Send",      show=True),
        Binding("ctrl+v",      "toggle_voice",   "Voice",     show=True),
        Binding("ctrl+c",      "interrupt_omni", "Interrupt", show=True),
        Binding("ctrl+r",      "refresh_all",    "Refresh",   show=True),
        Binding("ctrl+y",      "copy_response",  "Copy",      show=True),
        Binding("escape",      "app.quit",       "Quit",      show=False),
        Binding("ctrl+up",     "history_back",   "",          show=False),
        Binding("ctrl+down",   "history_fwd",    "",          show=False),
    ]

    # ── State ──────────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        super().__init__()
        self._proc:          subprocess.Popen | None = None
        self._master:        int | None = None
        self._out_q:         queue.Queue = queue.Queue()
        self._line_buf:      str = ""     # accumulates partial PTY lines
        self._buf_age:       int = 0      # drain cycles since last new queue data
        self._pending_cr:    bool = False  # saw \r, waiting to see if \n follows
        self._voice_active   = False
        self._history:       list[str] = []
        self._hist_pos:      int = -1
        self._hist_draft:    str = ""
        # Copy-response tracking
        self._last_ai_lines: list[str] = []   # lines of most recent AI reply
        self._in_ai_reply:   bool = False     # currently inside an ai › block
        # Plain-English state labels shown in ModeModelBar
        self._mode_label:    str = "Ask Me First"
        self._model_label:   str = "Best Quality (32b)"

    # ── Layout ─────────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield GPUBar()
                yield RamBar()
                yield ModeModelBar()

                # ── Think Style (model) ─────────────────────────────────────
                yield Label("  Think Style", classes="sec")
                yield SidebarBtn("■", "Best Quality",  "model_32b",
                                 "smartest, a bit slower")
                yield SidebarBtn("▸", "Balanced",      "model_14b",
                                 "fast and capable")
                yield SidebarBtn("◐", "Deep Thinker",  "model_reason",
                                 "hard problems, step-by-step")
                yield SidebarBtn("◌", "Casual Chat",   "model_chat",
                                 "quick back-and-forth")
                yield SidebarBtn("◎", "See Images",    "model_vision",
                                 "show it a picture")

                # ── Caution Level (mode) ────────────────────────────────────
                yield Label("  Caution Level", classes="sec")
                yield SidebarBtn("◉", "Ask Me First",  "mode_safe",
                                 "confirms before big changes")
                yield SidebarBtn("⚡", "Just Do It",    "mode_auto",
                                 "no confirmations, full speed")
                yield SidebarBtn("⚠", "Ask Everything","mode_paranoid",
                                 "maximum caution, ask always")

                # ── Self-Build (evolve) ─────────────────────────────────────
                yield Label("  Self-Build", classes="sec")
                yield SidebarBtn("▶", "Improve Itself","evolve_start",
                                 "start autonomous improvement")
                yield SidebarBtn("■", "Stop Improving","evolve_stop",
                                 "pause the improve loop")
                yield SidebarBtn("ℹ", "Progress Report","evolve_status",
                                 "see what it's been doing")

                # ── Quick Actions ───────────────────────────────────────────
                yield Label("  Quick Actions", classes="sec")
                yield SidebarBtn("✓", "Test OmniAI",   "task_selftest",
                                 "check everything works")
                yield SidebarBtn("⊞", "What's Running","task_sysinfo",
                                 "GPU, services, disk")
                yield SidebarBtn("◼", "Save Chat",     "task_save",
                                 "save this session to disk")
                yield SidebarBtn("✕", "Clear Chat",    "task_clear",
                                 "start fresh, wipe history")
                yield SidebarBtn("⎘", "Copy Reply",    "copy_response",
                                 "copy last AI answer")
                yield SidebarBtn("↺", "Restart Agent", "restart_omni",
                                 "reboot OmniAI process")

                # ── Services ────────────────────────────────────────────────
                yield Label("  Services", classes="sec")
                for name, label in SERVICES:
                    yield ServiceRow(name, label)
                yield OllamaRow()
                yield ComfyRow()

                # ── Docker Stack ────────────────────────────────────────────
                yield Label("  Docker Stack", classes="sec")
                yield SidebarBtn("▶", "Start Services","docker_start",
                                 "bring all containers up")
                yield SidebarBtn("■", "Stop Services", "docker_stop",
                                 "shut down all containers")

                # ── Launch App ──────────────────────────────────────────────
                yield Label("  Launch App", classes="sec")
                yield SidebarBtn("⚙", "Pipelines",     "open_pipelines",
                                 "Claude review API (port 9099)")
                yield SidebarBtn("⚙", "AI Web Search", "open_search",
                                 "AI-powered Perplexica")
                yield SidebarBtn("⚙", "Image Creator", "open_comfy",
                                 "ComfyUI / Stable Diffusion")
                yield SidebarBtn("⚙", "Automation",    "open_n8n",
                                 "n8n workflow builder")

                # @@INSERT_SIDEBAR@@

            with Vertical(id="main"):
                yield RichLog(id="chat_log", auto_scroll=True,
                              markup=False, highlight=False, wrap=True)
                yield ActivityBar(id="activity_bar")
                with Horizontal(id="input_row"):
                    yield TextArea(id="chat_input")
                    yield Button("🎤", id="voice_btn", variant="default")
                    yield Button("Send ⏎", id="send_btn", variant="primary")
                yield StatusBar(id="status_bar")

        yield Footer()

    def on_mount(self) -> None:
        self._start_omni()
        self.set_interval(0.05, self._drain)

    # ── Sidebar dispatcher ──────────────────────────────────────────────────────

    def sidebar_action(self, action_id: str) -> None:
        {
            # Docker
            "docker_start":   self._docker_start,
            "docker_stop":    self._docker_stop,
            # Open browser
            "open_pipelines": lambda: subprocess.Popen(["xdg-open", "http://localhost:9099"]),
            "open_search":    lambda: subprocess.Popen(["xdg-open", "http://localhost:3000"]),
            "open_comfy":     lambda: subprocess.Popen(["xdg-open", COMFYUI_URL]),
            "open_n8n":       lambda: subprocess.Popen(["xdg-open", "http://localhost:5678"]),
            # Agent
            "restart_omni":   self._start_omni,
            "refresh_all":    self.action_refresh_all,
            "copy_response":  self.action_copy_response,
            # Mode
            "mode_safe":      lambda: self._set_mode("cautious"),
            "mode_auto":      lambda: self._set_mode("auto"),
            "mode_paranoid":  lambda: self._set_mode("paranoid"),
            # Model
            "model_32b":      lambda: self._set_model("qwen2.5-coder:32b-instruct-q4_K_M"),
            "model_14b":      lambda: self._set_model("qwen2.5-coder:14b"),
            "model_reason":   lambda: self._set_model("deepseek-r1:14b"),
            "model_chat":     lambda: self._set_model("llama3.1:8b"),
            "model_vision":   lambda: self._set_model("qwen2.5vl:7b"),
            # Evolve
            "evolve_start":   lambda: self._write("/evolve"),
            "evolve_stop":    lambda: self._write("/evolve stop"),
            "evolve_status":  lambda: self._write("/evolve status"),
            # Quick tasks
            "task_selftest":  lambda: self._write("/test"),
            "task_sysinfo":   lambda: self._write("system_snapshot"),
            "task_save":      lambda: self._write("/save"),
            "task_clear":     lambda: self._write("/clear"),
            # @@INSERT_ACTION@@
        }.get(action_id, lambda: None)()

    # Plain-English label maps
    _MODE_LABELS = {
        "cautious": "Ask Me First",
        "auto":     "Just Do It",
        "paranoid": "Ask Everything",
    }
    _MODEL_LABELS = {
        "qwen2.5-coder:32b-instruct-q4_K_M": "Best Quality (32b)",
        "qwen2.5-coder:14b":                 "Balanced (14b)",
        "deepseek-r1:14b":                   "Deep Thinker (R1)",
        "llama3.1:8b":                       "Casual Chat (8b)",
        "qwen2.5vl:7b":                      "See Images (7b)",
    }

    def _set_mode(self, mode: str) -> None:
        self._mode_label = self._MODE_LABELS.get(mode, mode)
        self._write(f"/mode {mode}")
        self._sys(f"[Mode → {self._mode_label}]")
        self._refresh_state_bar()

    def _set_model(self, model_name: str) -> None:
        self._model_label = self._MODEL_LABELS.get(model_name, model_name)
        self._write(f"/model {model_name}")
        self._sys(f"[Model → {self._model_label}]")
        try:
            self.query_one("#status_bar", StatusBar).model_name = model_name
        except Exception:
            pass
        self._refresh_state_bar()

    def _refresh_state_bar(self) -> None:
        try:
            self.query_one(ModeModelBar).update_state(self._mode_label, self._model_label)
        except Exception:
            pass

    # ── OmniAI subprocess ──────────────────────────────────────────────────────

    def _start_omni(self) -> None:
        self._kill_omni()
        self._line_buf = ""
        self._buf_age  = 0
        try:
            import pty
            master, slave = pty.openpty()
            self._proc = subprocess.Popen(
                [PYTHON, OMNI_AI],
                stdin=slave, stdout=slave, stderr=slave,
                close_fds=True,
            )
            os.close(slave)
            self._master = master
            threading.Thread(target=self._read_loop,  daemon=True, name="omni-r").start()
            threading.Thread(target=self._watch_loop, daemon=True, name="omni-w").start()
            self._sys("[OmniAI started]")
        except Exception as e:
            self._sys(f"[ERROR starting OmniAI: {e}]")

    def _kill_omni(self) -> None:
        p = self._proc
        if p and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
        self._proc   = None
        self._master = None

    def _read_loop(self) -> None:
        while True:
            try:
                m = self._master
                if m is None:
                    break
                ready, _, _ = select.select([m], [], [], 0.05)
                if not ready:
                    continue
                chunk = os.read(m, 4096)
                if not chunk:
                    break
                self._out_q.put(chunk.decode("utf-8", errors="replace"))
            except OSError:
                break

    def _watch_loop(self) -> None:
        """Detect OmniAI crash and restart automatically."""
        while True:
            time.sleep(1.5)
            p = self._proc
            if p is None:
                break
            if p.poll() is not None:
                code = p.returncode
                self._out_q.put(f"\n[OmniAI exited ({code}). Reconnecting…]\n")
                time.sleep(2)
                self.call_from_thread(self._start_omni)
                break

    def _drain(self) -> None:
        """
        Buffer PTY output properly — OmniAI streams char-by-char so we must
        accumulate until \\n before writing to the log.

        \\r (carriage return, used by the spinner) clears the current partial
        line so spinner animation frames never appear in the log.
        """
        log = self.query_one("#chat_log", RichLog)

        new_text = ""
        while not self._out_q.empty():
            new_text += self._out_q.get_nowait()

        if not new_text:
            # Flush stale buffer after ~2 s of silence (end-of-response)
            # but ONLY if it doesn't look like a spinner frame.
            self._buf_age += 1
            if self._buf_age >= 40:
                s = self._line_buf.strip()
                if s and not _is_spinner_line(s) and not self._pending_cr:
                    log.write(colorize_line(s))
                self._line_buf   = ""
                self._pending_cr = False
                self._buf_age    = 0
            return

        self._buf_age = 0
        clean = strip_ansi(new_text)

        # char-by-char:
        #   \r\n  → normal line ending (Rich/terminal) → commit line
        #   \r    alone (spinner overwrite) → discard current partial line
        #   \n    → commit current line
        #   else  → accumulate
        for ch in clean:
            if ch == "\r":
                self._pending_cr = True   # wait to see if \n follows
            elif ch == "\n":
                # \r\n  → real newline; bare \n → also real newline
                # either way commit the buffer
                self._pending_cr = False
                s = self._line_buf.strip()
                if s and not _is_spinner_line(s):
                    log.write(colorize_line(s))
                    # ── ActivityBar updates ────────────────────────────────
                    try:
                        ab = self.query_one("#activity_bar", ActivityBar)
                        if s.startswith("ai › "):
                            # First token of AI reply → mark done
                            ab.done()
                        elif "⚙" in s:
                            # Tool call line — extract action name
                            # Format: "  ⚙ tool_name(args…)" or "⚙ Calling tool_name"
                            action = s.replace("⚙", "").strip()
                            # Trim arg parens for display
                            if "(" in action:
                                action = action[:action.index("(")].strip()
                            ab.set_action(action or "Working")
                    except Exception:
                        pass
                    # ── AI copy tracking ───────────────────────────────────
                    if s.startswith("ai › "):
                        self._in_ai_reply   = True
                        self._last_ai_lines = [s[5:]]
                    elif self._in_ai_reply:
                        if s.startswith("you › ") or s.startswith("["):
                            self._in_ai_reply = False
                        else:
                            self._last_ai_lines.append(s)
                self._line_buf = ""
            else:
                if self._pending_cr:
                    # bare \r followed by non-\n = spinner overwrite → discard
                    self._line_buf   = ""
                    self._pending_cr = False
                self._line_buf += ch

    def _write(self, text: str) -> None:
        m = self._master
        if m is None:
            self._sys("[Not connected — use Restart Agent]")
            return
        try:
            os.write(m, (text + "\n").encode())
        except OSError:
            self._sys("[Write error — reconnecting…]")
            self._start_omni()

    def _sys(self, msg: str) -> None:
        self._out_q.put(f"{msg}\n")

    # ── Input & command history ────────────────────────────────────────────────

    def action_submit_input(self) -> None:
        ta = self.query_one("#chat_input", TextArea)
        self._submit(ta.text)
        ta.clear()
        self._hist_pos   = -1
        self._hist_draft = ""

    @on(Button.Pressed, "#send_btn")
    def _on_send(self) -> None:
        ta = self.query_one("#chat_input", TextArea)
        self._submit(ta.text)
        ta.clear()
        self._hist_pos = -1

    def _submit(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if not self._history or self._history[0] != text:
            self._history.insert(0, text)
            if len(self._history) > HISTORY_MAX:
                self._history.pop()
        self.query_one("#chat_log", RichLog).write(colorize_line(f"you › {text}"))
        try:
            self.query_one("#activity_bar", ActivityBar).start()
        except Exception:
            pass
        self._write(text)

    def action_history_back(self) -> None:
        ta = self.query_one("#chat_input", TextArea)
        if not self._history:
            return
        if self._hist_pos == -1:
            self._hist_draft = ta.text
        self._hist_pos = min(self._hist_pos + 1, len(self._history) - 1)
        ta.clear()
        ta.insert(self._history[self._hist_pos])

    def action_history_fwd(self) -> None:
        ta = self.query_one("#chat_input", TextArea)
        if self._hist_pos <= 0:
            self._hist_pos = -1
            ta.clear()
            ta.insert(self._hist_draft)
        else:
            self._hist_pos -= 1
            ta.clear()
            ta.insert(self._history[self._hist_pos])

    # ── Keyboard actions ───────────────────────────────────────────────────────

    def action_copy_response(self) -> None:
        if not self._last_ai_lines:
            self._sys("[Nothing to copy yet — ask OmniAI something first]")
            return
        text = "\n".join(self._last_ai_lines)
        ok   = _clipboard_copy(text)
        if ok:
            self._sys(f"[⎘ Copied {len(text)} chars to clipboard]")
        else:
            self._sys("[⎘ Copy failed — install xclip or xsel]")

    def action_interrupt_omni(self) -> None:
        m = self._master
        if m is not None:
            try:
                os.write(m, b"\x03")
                self._sys("[Interrupted]")
            except OSError:
                pass

    def action_refresh_all(self) -> None:
        for w in self.query(ServiceRow):
            w._refresh()
        for cls in (OllamaRow, ComfyRow, GPUBar):
            try:
                self.query_one(cls)._refresh()
            except Exception:
                pass

    # ── Voice ──────────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#voice_btn")
    def _on_voice_btn(self) -> None:
        self.action_toggle_voice()

    def action_toggle_voice(self) -> None:
        if self._voice_active:
            self._stop_voice()
        else:
            self._start_voice()

    def _start_voice(self) -> None:
        self._voice_active = True
        self.query_one("#voice_btn", Button).label = "⏹"
        self._sys("[🎤 Recording 5s…]")
        threading.Thread(target=self._record_voice, daemon=True, name="voice").start()

    def _stop_voice(self) -> None:
        self._voice_active = False
        try:
            self.query_one("#voice_btn", Button).label = "🎤"
        except Exception:
            pass

    def _record_voice(self) -> None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        wav = tmp.name
        rec = (
            "import sounddevice as sd,numpy as np,scipy.io.wavfile as wf\n"
            "R=16000;c=[]\n"
            "with sd.InputStream(samplerate=R,channels=1,dtype='float32') as s:\n"
            "    [c.append(s.read(1024)[0]) for _ in range(int(R/1024*5))]\n"
            f"wf.write('{wav}',R,np.concatenate(c).flatten())\n"
        )
        trn = (
            "from faster_whisper import WhisperModel\n"
            "m=WhisperModel('large-v3-turbo',device='cuda',compute_type='float16')\n"
            f"segs,_=m.transcribe('{wav}',language='en')\n"
            "print(' '.join(s.text.strip() for s in segs).strip())\n"
        )
        try:
            subprocess.run([VOICE_PY, "-c", rec],  capture_output=True, timeout=10)
            r = subprocess.run([VOICE_PY, "-c", trn], capture_output=True,
                               text=True, timeout=30)
            text = r.stdout.strip()
        except Exception as e:
            text = ""
            self._sys(f"[🎤 Error: {e}]")
        finally:
            try:
                os.unlink(wav)
            except OSError:
                pass
        if text:
            self._sys(f"[🎤 Transcribed — sending…]")
            self.call_from_thread(self._submit, text)
        else:
            self._sys("[🎤 No speech detected]")
        self.call_from_thread(self._stop_voice)

    # ── Docker helpers ─────────────────────────────────────────────────────────

    def _docker_start(self) -> None:
        subprocess.Popen("cd ~/omni-stack && docker compose up -d", shell=True)
        self._sys("[Starting Docker stack…]")

    def _docker_stop(self) -> None:
        subprocess.Popen("cd ~/omni-stack && docker compose down", shell=True)
        self._sys("[Stopping Docker stack…]")

    # ── Cleanup ────────────────────────────────────────────────────────────────

    def on_unmount(self) -> None:
        self._kill_omni()


if __name__ == "__main__":
    signal.signal(signal.SIGHUP,  lambda *_: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    OmniPanel().run()
