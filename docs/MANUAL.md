# CLOD(1) — Local AI CLI

## NAME

**clod** — terminal CLI for local AI inference via Ollama, with optional cloud model review through LiteLLM

## SYNOPSIS

```
clod [OPTIONS]
clod -p PROMPT [OPTIONS]
clod --index [PATH]
clod --version
```

## DESCRIPTION

**clod** is an interactive REPL that routes prompts to local LLMs (Ollama) and optionally through two-stage pipelines where a local model drafts and a cloud model (Claude) reviews. It provides tool use (shell, files, web search), GPU-aware model selection, token budget tracking, intent-based routing, image/video generation, Docker service management, and project indexing.

On first run, clod walks through environment setup (GPU driver detection, API keys, `.env` creation) and offers to start Docker services.

## OPTIONS

| Flag | Description |
|------|-------------|
| `-p, --print PROMPT` | One-shot mode: send PROMPT, print response, exit |
| `-m, --model MODEL` | Override the default model for this session |
| `--pipeline NAME` | Use a two-stage pipeline (`code_review`, `reason_review`, `chat_assist`) |
| `-s, --system PROMPT` | Set a custom system prompt |
| `--tools` | Enable tool use (bash, file read/write, web search) |
| `--no-stream` | Disable streaming output |
| `--index [PATH]` | Index projects under PATH, generating CLAUDE.md and README.md per project |
| `--auto-model` | Auto-select model based on detected GPU VRAM |
| `--version` | Print version and exit |

## REPL COMMANDS

All commands start with `/` in the interactive REPL.

### Session

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/clear` | Clear conversation history |
| `/save [FILE]` | Save conversation to JSON file |
| `/exit`, `/quit` | Exit clod |

### Model & Pipeline

| Command | Description |
|---------|-------------|
| `/model [NAME]` | Switch model (no arg = show current) |
| `/pipeline [NAME\|off]` | Switch pipeline or disable |
| `/intent [auto\|verbose\|TEXT]` | Control auto-classification or classify TEXT |

### Toggles

| Command | Description |
|---------|-------------|
| `/tools [on\|off]` | Toggle tool use |
| `/offline [on\|off]` | Toggle offline mode (local only, no cloud calls) |
| `/search [on\|off]` | Toggle SearXNG web search |

### Generation

| Command | Description |
|---------|-------------|
| `/generate image PROMPT` | Generate image via Stable Diffusion |
| `/generate video PROMPT` | Generate video via ComfyUI |

### Stable Diffusion / ComfyUI

| Command | Description |
|---------|-------------|
| `/sd` | Show current SD mode and status |
| `/sd image` | Switch to AUTOMATIC1111 image mode |
| `/sd video` | Switch to ComfyUI video mode |
| `/sd stop` | Stop all SD services (free VRAM) |
| `/sd start` | Start last-active SD mode |

### Docker Services

| Command | Description |
|---------|-------------|
| `/services` | Show health status of all services |
| `/services start` | Start missing services (`docker compose up -d`) |
| `/services stop` | Stop all services (`docker compose down`) |
| `/services reset [NAME\|all] [--yes]` | Wipe data and redeploy service(s) |

### System Info

| Command | Description |
|---------|-------------|
| `/system PROMPT` | Set system prompt for session |
| `/tokens` | Show Claude token usage and budget |
| `/gpu` | Show GPU VRAM and recommended model |
| `/gpu use` | Auto-switch to recommended model |
| `/mcp` | Show MCP filesystem server status |
| `/index [PATH]` | Index projects under PATH |

## TOOLS

When `--tools` or `/tools on` is active, the LLM can call:

| Tool | Parameters | Description |
|------|-----------|-------------|
| `bash_exec` | `command`, `timeout` (default 30s) | Execute shell command (requires user confirmation) |
| `read_file` | `path`, `lines` (0=all) | Read file contents |
| `write_file` | `path`, `content`, `append` | Write or append to file |
| `web_search` | `query`, `count` (default 5) | Search via local SearXNG |

## PIPELINES

Two-stage flow: local Ollama model drafts, cloud model reviews.

| Pipeline | Local Model | Cloud Model | Use Case |
|----------|------------|-------------|----------|
| `code_review` | qwen2.5-coder:14b | claude-sonnet | Code, debugging, architecture |
| `reason_review` | deepseek-r1:14b | claude-sonnet | Analysis, planning, reasoning |
| `chat_assist` | llama3.1:8b | claude-haiku | General Q&A, writing |

Configure per-pipeline via Open-WebUI Valves: `LOCAL_MODEL`, `CLAUDE_MODEL`, `SKIP_LOCAL`, `REVIEW_SYSTEM`.

## MODELS

### Local (Ollama)

| Model | VRAM | Purpose |
|-------|------|---------|
| `qwen2.5-coder:14b` | ~10 GB | Code generation (default) |
| `qwen2.5-coder:32b-instruct-q4_K_M` | ~20 GB | Large code (needs partial offload on 16 GB) |
| `deepseek-r1:14b` | ~9 GB | Reasoning, chain-of-thought |
| `llama3.1:8b` | ~6 GB | Fast conversational |
| `qwen2.5vl:7b` | ~6 GB | Vision/image understanding |

### Cloud (via LiteLLM)

Cloud models are detected by prefix: `claude-*`, `gpt-*`, `o1-*`, `o3-*`, `gemini-*`, `groq-*`, `together-*`. Requires corresponding API key in `.env`.

## INTENT CLASSIFICATION

Automatic model routing based on prompt intent.

**Layer 1 — Keyword/regex rules** (sub-1ms):
- `image_gen`: generate/create + image/picture/photo
- `image_edit`: edit/modify + image/picture
- `video_gen`: generate/create + video/animation
- `vision`: describe/look at + image/screenshot
- `code`: write/implement/debug + function/class/code
- `reason`: explain why/analyze/compare

**Layer 2 — ONNX embedding similarity** (<100ms CPU):
Uses quantized all-MiniLM-L6-v2 model against route centroids.

Control: `/intent auto` (enable), `/intent verbose` (debug), `/intent TEXT` (test).

## TOKEN BUDGET

Tracks cumulative Claude API tokens per session (default: 100,000).

| Threshold | Behavior |
|-----------|----------|
| >= 80% | Yellow warning in header |
| >= 95% | Prompt to switch to offline mode |
| 100% | Auto-switch to offline mode |

Configure `token_budget` in `%APPDATA%\clod\config.json`.

## MCP FILESYSTEM SERVER

On startup, clod optionally starts an HTTP filesystem server on port 8765 (localhost-only).

| Endpoint | Method | Action |
|----------|--------|--------|
| `/list` | GET | List files in workspace |
| `/<path>` | GET | Read file |
| `/<path>` | POST | Write file |
| `/<path>` | DELETE | Delete file |

Can be connected to Open-WebUI via `tools/clod_mcp_tool.py` (shared volume or HTTP mode).

## CONFIGURATION

### Config file

`%APPDATA%\clod\config.json` (auto-created):

```json
{
  "ollama_url":    "http://localhost:11434",
  "litellm_url":   "http://localhost:4000",
  "litellm_key":   "sk-local-dev",
  "pipelines_url": "http://localhost:9099",
  "chroma_url":    "http://localhost:8000",
  "searxng_url":   "http://localhost:8080",
  "default_model": "qwen2.5-coder:14b",
  "token_budget":  100000,
  "mcp_port":      8765
}
```

### Environment (.env)

Key variables (see `.env.example` for full list):

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Required for Claude models |
| `OPENAI_API_KEY` | Optional, for GPT models |
| `OLLAMA_GPU_OVERHEAD` | VRAM headroom (bytes, default 512 MB) |
| `OLLAMA_KEEP_ALIVE` | Model unload timeout (default 5m) |
| `BASE_DIR` | Host data storage root |
| `SHARED_DIR` | Shared workspace for MCP tool |

## DOCKER SERVICES

| Service | Port | Purpose |
|---------|------|---------|
| nginx | 80 | Reverse proxy |
| ollama | 11434 | Local LLM inference |
| litellm | 4000 | Unified LLM gateway |
| open-webui | 8081 | Chat UI |
| pipelines | 9099 | Two-stage routing |
| searxng | 8080 | Private web search |
| chroma | 8000 | Vector DB |
| stable-diffusion | 7860 | Image generation (profile: image) |
| comfyui | 8188 | Video generation (profile: video) |
| n8n | 5678 | Automation (profile: automation) |

## PROJECT INDEXING

`clod --index PATH` or `/index PATH` walks a directory tree, detects project roots by signals (`.git`, `package.json`, `Cargo.toml`, `Dockerfile`, etc.), and generates:

- **CLAUDE.md** per project (AI-readable context)
- **README.md** per project (human-readable)

Uses claude-sonnet for generation.

## FILES

| Path | Description |
|------|-------------|
| `clod.py` | Main CLI application |
| `intent.py` | Intent classification engine |
| `mcp_server.py` | MCP filesystem server |
| `docker-compose.yml` | Docker service definitions |
| `.env` / `.env.example` | Environment configuration |
| `pipelines/*.py` | Pipeline definitions |
| `models/intent/` | ONNX model, tokenizer, route embeddings |
| `%APPDATA%\clod\config.json` | User configuration |

## EXAMPLES

```bash
# Interactive REPL
clod

# One-shot with tools
clod --tools -p "list all Python files in this directory"

# Pipeline mode
clod --pipeline code_review -p "review this function for bugs"

# Switch model mid-session
> /model deepseek-r1:14b

# Check services and start if needed
> /services
> /services start

# Generate an image
> /generate image a sunset over mountains in watercolor style

# Auto-select model for your GPU
> /gpu use

# Index all projects
clod --index C:\projects
```

## VERSION

clod v1.0.0

## SEE ALSO

- README.md — Full project documentation with screenshots
- .env.example — Complete environment variable reference
- docker-compose.yml — Service definitions and networking
