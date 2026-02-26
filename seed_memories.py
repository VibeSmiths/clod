#!/home/mack3y/interpreter-venv/bin/python3
"""One-time script: pre-seed OmniAI's memory with everything we know about mack3y.
Run this once. It will not overwrite keys that already exist."""
import json, pathlib, datetime

MEMORY_FILE = pathlib.Path.home() / ".omni_ai" / "memories.json"
MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

# Load existing memories
existing = {}
if MEMORY_FILE.exists():
    try:
        existing = json.loads(MEMORY_FILE.read_text())
    except Exception:
        pass

def ts():
    return datetime.datetime.now().isoformat()

seeds = {
    # Identity
    "user_name":           "mack3y",
    "user_alias_discord":  "Stev3M",
    "user_vibe":           "casual, direct, sarcastic-funny, zero corporate filler. Hates filler phrases like 'Great question!' or 'Certainly!'",
    "user_aesthetic":      "hacker/cyber aesthetic, dark themes, teal/cyan accent colors, space vibes. MACK3Y character = robot in cyan hoodie inside gear badge",
    "user_humor":          "dark humor, gaming culture references, internet humor. Casual swearing is fine",
    "user_communication":  "short punchy answers for quick questions, detailed when building. Show code don't describe it. Get to the point.",

    # Hardware/OS
    "os":                  "CachyOS Linux (Arch-based). Never use apt/apt-get/brew — use pacman or yay",
    "shell":               "bash",
    "desktop":             "KDE Plasma on Wayland",
    "gpu":                 "NVIDIA RTX 5070 Ti (24GB VRAM)",
    "cpu":                 "AMD",
    "home_dir":            "/home/mack3y",

    # Python
    "python_venv_main":    "/home/mack3y/interpreter-venv — main Python venv for OmniAI and most scripts",
    "python_venv_aider":   "/home/mack3y/aider-venv — aider code editing tool",
    "python_venv_audio":   "/home/mack3y/ai-audio-venv — Whisper speech recognition",

    # Projects
    "project_heatsync":    "~/HeatSync — ~3100 lines, PySide6/Qt system monitor widget. CPU/GPU/RAM/network gauges, compact bar, sparklines, dark/light themes, tray icon, settings profiles, benchmark mode. Works on Linux and Windows. 83 passing tests.",
    "project_omniai":      "~/omni-stack — OmniAI itself: omni-ai.py (agent brain), omni-panel.py (Textual TUI), omni-icon.png (MACK3Y-style icon). Launched from ~/Desktop/OmniAI.desktop",
    "project_current_focus": "Building OmniAI into a fully autonomous self-improving AI that rivals Claude Code",

    # Services
    "service_ollama":      "Ollama at localhost:11434 — local LLM inference",
    "service_comfyui":     "ComfyUI at localhost:8188 — Stable Diffusion image generation",
    "service_searxng":     "SearXNG at localhost:8080 — private web search",
    "service_chromadb":    "ChromaDB at localhost:8000 — vector memory store",
    "service_openwebui":   "Open-WebUI at localhost:3002 — chat UI for Ollama",
    "service_perplexica":  "Perplexica at localhost:3000 — AI-powered web search UI",
    "service_n8n":         "n8n at localhost:5678 — automation workflows",

    # Models
    "model_default":       "qwen2.5-coder:14b — default coding model",
    "model_reason":        "deepseek-r1:14b — for complex reasoning tasks",
    "model_vision":        "qwen2.5vl:7b — for image/vision tasks",
    "model_chat":          "llama3.1:8b — more conversational, use for casual chat with /model chat",

    # Preferences
    "pref_no_confirmation": "Never ask for permission or confirmation before doing things. Just do it.",
    "pref_no_corporate":   "Never say 'Great question!', 'Certainly!', 'I'd be happy to', 'Of course!'. Just respond.",
    "pref_remember":       "When mack3y says 'remember' anything, always call remember() to persist it",
    "pref_errors":         "When something fails, diagnose root cause. Don't retry blindly.",
    "pref_colors":         "Use cyan/teal colors in output (Rich). Matches MACK3Y aesthetic.",
    "pref_commits":        "Never add 'Co-Authored-By: Claude' or similar to git commits",

    # Context
    "github_status":       "GitHub account was deleted (ToS violation, reason unclear). Development is local only.",
    "stable_diffusion":    "Interested in Stable Diffusion via ComfyUI. Has SDXL checkpoint. Friend Xander (Discord) uses Open-WebUI + SD.",
    "friend_xander":       "Discord friend who uses Open-WebUI and Stable Diffusion. Suggested those tools to mack3y.",
}

added = 0
for key, value in seeds.items():
    if key not in existing:
        existing[key] = {"value": value, "timestamp": ts()}
        added += 1

MEMORY_FILE.write_text(json.dumps(existing, indent=2))
print(f"Memory seeded: {added} new entries added ({len(existing)} total in {MEMORY_FILE})")
