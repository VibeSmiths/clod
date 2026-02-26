# OmniAI — Project Context

This is **OmniAI**, $USER's autonomous local AI agent / vibecoder home base.
It is a completely separate project from HeatSync.

## What it is
A Claude Code-style autonomous AI agent that runs entirely locally on CachyOS Linux.
It routes tasks to local LLMs via Ollama, executes shell commands, writes/edits code,
searches the web, generates images via ComfyUI, manages its own memory, and can
**add new tools to itself** (self_improve → restart_self).

Launched from: `~/Desktop/OmniAI.desktop` → double-click opens Konsole with the TUI.

## Files

| File | Purpose |
|------|---------|
| `omni-ai.py` | The agent brain (~2100 lines). LLM loop, all tools, streaming, REPL, evolve mode |
| `omni-panel.py` | Textual TUI (~750 lines). Embeds omni-ai.py via PTY, sidebar, chat log |
| `omni-icon.png` | 256×256 $USER-style icon (dark bg, gear, robot in cyan hoodie) |
| `make_icon.py` | PIL script that regenerates the icon |
| `seed_memories.py` | One-time script to pre-populate ~/.omni_ai/memories.json |
| `launch-omni.sh` | Konsole launcher (hide menubar/tabbar, --nofork) |
| `ai.sh` | CLI shortcut: `ai "do this"` or just `ai` for interactive mode |
| `docker-compose.yml` | Docker stack: Open-WebUI, Perplexica, SearXNG, n8n, ChromaDB |

## Architecture

```
omni-panel.py (Textual TUI)
  └── embeds omni-ai.py via pty.openpty() subprocess
        └── OmniAI class → Ollama HTTP API → tool loop → streaming REPL
              └── ~/.omni_ai/memories.json    (persistent KV memory)
              └── ~/.omni_ai/sessions/        (saved conversation sessions)
              └── ~/.omni_ai/evolving.json    (evolution loop state, survives restarts)
              └── ~/.omni_ai/evolution_log.json
              └── ~/omni-stack/backups/       (auto-backups before self_improve)
```

## Key Systems

### LLM / Models
- Default: `qwen2.5-coder:14b` (Ollama at localhost:11434)
- Reason: `deepseek-r1:14b`
- Vision: `qwen2.5vl:7b`
- Chat: `llama3.1:8b` (more conversational)
- Big: `qwen2.5-coder:32b-instruct-q4_K_M` (RTX 5070 Ti has 24GB, can run this)
- Switch with `/model <name>` in REPL

### Tool System
- 40+ tools: shell, file I/O, web search/scrape/research, git, image gen, memory, docker
- `self_improve(tool_name, desc, function_code, params)` — splices new tools into omni-ai.py
- Three insertion markers: `# @@INSERT_TOOL@@`, `# @@INSERT_FUNCTION@@`, `# @@INSERT_MAPPING@@`
- Always `backup_self()` before `self_improve()`, always `run_self_test()` after
- `restart_self()` uses `os.execv` to hot-reload new tools

### Approval / Confirmation Gate
- Mode `cautious` (default): asks before `self_improve`, `rollback_self`, destructive shell, big writes
- Mode `auto`: no prompts
- Mode `paranoid`: asks for almost everything
- Switch with `/mode auto|cautious|paranoid`
- Press `a` at any prompt to approve that tool type for the whole session

### Evolution Loop (`/evolve`)
- Autonomous self-improvement: audit → research → plan → (user approves) → implement → test → restart
- State persists in `~/.omni_ai/evolving.json` — survives `restart_self()` and auto-resumes
- Each cycle outputs `PLAN:` first, user reviews before anything is touched
- `/evolve stop` to exit, `/evolve status` to see history, `/evolve resume` to continue

### Spinner
- Braille/diamond frames + 80+ funny words ("Yak shaving…", "Galaxy-braining…", "Force pushing…")
- Cycles colors: bright cyan → cyan → blue → magenta → green → yellow
- `\r` overwrite mechanism — panel filters these out via `_pending_cr` flag

### Panel (`omni-panel.py`) Key Patterns
- PTY streaming: char-by-char → `_line_buf` → commit on `\n`, discard spinner on bare `\r`
- `\r\n` (Rich output line endings) = real newline, NOT spinner discard (`_pending_cr` flag)
- `SidebarBtn`: extends `Static`, calls `self.update()` in `on_mount()` — NOT in `__init__`
- Ctrl+Y copies last AI reply to clipboard (xclip → xsel → wl-copy)
- $USER theme: dark space bg `#050510`, teal/cyan borders `#1e3e3e` / `#64dcbc`

## Services (Docker)
| Service | URL | Purpose |
|---------|-----|---------|
| Open-WebUI | localhost:3002 | Chat UI for Ollama models |
| Perplexica | localhost:3000 | AI-powered web search |
| SearXNG | localhost:8080 | Private search (used by search_web tool) |
| n8n | localhost:5678 | Automation workflows |
| ChromaDB | localhost:8000 | Vector memory (semantic_recall tool) |
| ComfyUI | localhost:8188 | Stable Diffusion image generation |
| Ollama | localhost:11434 | Local LLM inference |

## User Preferences
- **$USER** (online: Stev3M) — casual, direct, no corporate filler
- Teal/cyan aesthetic, $USER robot character (robot in cyan hoodie, gear badge)
- Never add "Co-Authored-By: Claude" to commits
- Show code don't describe it
- Ask before big changes, auto for small ones
- `/mode cautious` is the right default

## Common Tasks

### Run OmniAI
```bash
# Full TUI (recommended):
~/Desktop/OmniAI.desktop   # double-click

# CLI:
ai "build me a FastAPI server"
ai   # interactive REPL

# Direct:
~/interpreter-venv/bin/python3 ~/omni-stack/omni-ai.py
```

### Regenerate icon
```bash
~/interpreter-venv/bin/python3 ~/omni-stack/make_icon.py
```

### Re-seed memories (adds missing keys, never overwrites)
```bash
~/interpreter-venv/bin/python3 ~/omni-stack/seed_memories.py
```

### Add a new tool manually
1. Write the function in `omni-ai.py` above `# @@INSERT_FUNCTION@@`
2. Add the name to `TOOLS` list above `# @@INSERT_TOOL@@`
3. Add to `TOOL_FN_MAP` above `# @@INSERT_MAPPING@@`
4. Add description to `SYSTEM_PROMPT` AVAILABLE TOOLS section

### Start Docker stack
```bash
cd ~/omni-stack && docker compose up -d
```

## Python Environment
```
~/interpreter-venv/   # main venv — omni-ai.py, omni-panel.py
~/aider-venv/         # aider code editor
~/ai-audio-venv/      # faster-whisper voice recognition
```
Key packages in interpreter-venv: `requests`, `rich`, `textual`, `pillow`, `chromadb`

## Known Patterns / Gotchas
- `os.execv` restart works but loses any in-memory state not saved to disk
- Evolution state (`evolving.json`) must be saved BEFORE calling `restart_self()`
- Rich Columns renders side-by-side in real terminal but collapses when piped
- Panel `_drain`: Rich uses `\r\n` line endings → must handle `_pending_cr` to not discard banner lines
- `str.replace(old, new, 1)` — always count=1 in `self_improve` or the markers inside the function body get corrupted
- `isHidden()` not `isVisible()` for Qt widget tests without parent chain (not relevant here, HeatSync pattern)
