# OmniAI

Autonomous local AI vibecoder — runs entirely on your machine.
Routes tasks to local LLMs via Ollama, executes shell commands, writes/edits code,
searches the web, generates images via ComfyUI, manages its own memory, and can
**add new tools to itself**.

**Stack:** CachyOS Linux · RTX 5070 Ti · Ollama · qwen2.5-coder:32b

---

## Quick Start

### Full TUI (recommended)

```bash
# Double-click the desktop shortcut, or:
~/Desktop/OmniAI.desktop
```

### CLI from any terminal

```bash
ai "build me a FastAPI server"   # single task
ai                                # interactive REPL
```

---

## Docker

### Prerequisites

- Docker + Docker Compose installed
- [Ollama](https://ollama.ai) running on the host (`ollama serve`)
- An Anthropic API key for the Claude review pipeline (optional but recommended)

### Build the OmniAI agent image

```bash
cd ~/omni-stack
docker build -t omni-stack .
```

### Run — interactive REPL

```bash
docker run -it --rm \
  --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -v ~/.omni_ai:/root/.omni_ai \
  -v ~/omni-stack/backups:/app/backups \
  omni-stack
```

### Run — single command

```bash
docker run --rm \
  --add-host=host.docker.internal:host-gateway \
  -e OLLAMA_URL=http://host.docker.internal:11434 \
  -v ~/.omni_ai:/root/.omni_ai \
  omni-stack "explain this codebase"
```

### Run — connected to the full stack (services also in Docker)

```bash
# Start services first
docker compose up -d

# Run agent on the same network
docker run -it --rm \
  --network=host \
  -e OLLAMA_URL=http://localhost:11434 \
  -v ~/.omni_ai:/root/.omni_ai \
  -v ~/omni-stack/backups:/app/backups \
  omni-stack
```

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://host.docker.internal:11434` | Ollama API endpoint |
| `SEARXNG_URL` | `http://searxng:8080` | SearXNG search endpoint |
| `CHROMA_URL` | `http://chroma:8000` | ChromaDB vector store |
| `PIPELINES_URL` | `http://omni-pipelines:9099` | Claude review pipeline API |

### Persistent volumes

| Mount | Purpose |
|---|---|
| `~/.omni_ai:/root/.omni_ai` | Memory, sessions, API keys |
| `~/omni-stack/backups:/app/backups` | Self-improvement backups |

---

## Services Stack

Start / stop all services:

```bash
cd ~/omni-stack
docker compose up -d      # start
docker compose down       # stop
docker compose logs -f    # watch logs
```

| Service | URL | Purpose |
|---|---|---|
| **omni-pipelines** | localhost:9099 | Claude review + multi-LLM routing |
| **Perplexica** | localhost:3000 | AI-powered web search |
| **SearXNG** | localhost:8080 | Private search (used by search_web tool) |
| **n8n** | localhost:5678 | Automation workflows |
| **ChromaDB** | localhost:8000 | Vector memory (semantic_recall tool) |
| **ComfyUI** | localhost:8188 | Stable Diffusion image generation (host) |
| **Ollama** | localhost:11434 | Local LLM inference (host) |

---

## Claude Review Pipeline

The `omni-pipelines` service runs the Claude review pipe automatically.

**What it does:** After OmniAI finishes a local Ollama iteration, the pipeline
sends the draft to Claude which reviews it for bugs, improves formatting, and
appends a next-steps plan before returning the final response.

### Setup

1. Add your Anthropic API key to `.env`:

```bash
# ~/omni-stack/.env
ANTHROPIC_API_KEY=sk-ant-...
```

2. Restart the stack:

```bash
docker compose up -d omni-pipelines
```

3. The pipeline is now live at `http://localhost:9099`.
   Call it from OmniAI with:

```
ask_llm("pipelines", "your message", model="claude_review")
```

Or set it as the default review endpoint in omni-ai.py via `/model`.

### Valves (configurable per-request)

| Valve | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Your Anthropic API key |
| `CLAUDE_MODEL` | `claude-opus-4-6` | Claude model to use for review |
| `LOCAL_MODEL` | `qwen2.5-coder:32b-instruct-q4_K_M` | Local Ollama model for draft |
| `OLLAMA_URL` | `http://host-gateway:11434` | Ollama endpoint |
| `SKIP_LOCAL` | `false` | Set to `true` to call Claude directly |

---

## Development

### Python environments

```
/home/mack3y/interpreter-venv/   # OmniAI agent + panel
/home/mack3y/aider-venv/         # Aider code editor
/home/mack3y/ai-audio-venv/      # faster-whisper voice recognition
```

### Key files

| File | Purpose |
|---|---|
| `omni-ai.py` | Agent brain — LLM loop, 48+ tools, self-improvement |
| `omni-panel.py` | Textual TUI — embeds agent via PTY |
| `omni-ctl.py` | Simple CLI control panel |
| `docker-compose.yml` | Service stack |
| `Dockerfile` | OmniAI agent container |
| `pipelines/claude_review_pipe.py` | Claude review pipeline |

### Add a new tool manually

1. Write the function in `omni-ai.py` above `# @@INSERT_FUNCTION@@`
2. Add the name to `TOOLS` list above `# @@INSERT_TOOL@@`
3. Add to `TOOL_FN_MAP` above `# @@INSERT_MAPPING@@`

Or ask OmniAI to do it: `self_improve("tool_name", "desc", code, params)`

### Self-improvement

```
/evolve          — start autonomous improvement loop
/evolve stop     — pause
/evolve status   — check progress
/test            — run self-test
```
