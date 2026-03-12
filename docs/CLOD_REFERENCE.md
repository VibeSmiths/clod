# clod — AI Agent Reference

> Machine-readable reference for AI assistants working with the clod codebase.
> Structured for fast lookup, not prose.

## Identity

- **What**: Local AI CLI — terminal REPL routing to Ollama (local LLMs) with optional cloud review via LiteLLM
- **Main file**: `clod.py` (~3,745 lines, 888 statements)
- **Language**: Python 3.11+
- **Version**: 1.0.0
- **Entry point**: `clod.py:main()` (line ~3640)
- **Build**: PyInstaller → `dist/clod.exe` (spec: `clod.spec`)

## Architecture

```
User Input
    │
    ├─ Intent Classification (intent.py)
    │   ├─ Layer 1: regex rules (sub-1ms)
    │   └─ Layer 2: ONNX embedding similarity (<100ms)
    │
    ├─ Slash Command? → handle_slash() [line ~2888]
    │
    ├─ Pipeline mode? → pipelines service (localhost:9099)
    │   └─ Stage 1: Ollama draft → Stage 2: Claude review
    │
    └─ Direct inference → Ollama (localhost:11434)
        └─ Or cloud model → LiteLLM (localhost:4000)

Tools (when enabled):
    bash_exec, read_file, write_file, web_search
    └─ Executed locally, results fed back to LLM
```

## CLI Arguments (argparse, line ~3649)

```
-p, --print PROMPT     One-shot mode
-m, --model MODEL      Model override
--pipeline NAME        code_review | reason_review | chat_assist
-s, --system PROMPT    System prompt
--tools                Enable tool use
--no-stream            Disable streaming
--index [PATH]         Project indexer
--auto-model           GPU-based model selection
--version              Print version
```

## Slash Commands (handle_slash, line ~2888)

```
# Session
/help  /clear  /save [FILE]  /exit  /quit

# Model & Pipeline
/model [NAME]              Show or switch model
/pipeline [NAME|off]       Show, switch, or disable pipeline
/intent [auto|verbose|TEXT] Intent classification control

# Toggles
/tools [on|off]            Tool use
/offline [on|off]          Offline mode (local only)
/search [on|off]           Web search

# Generation
/generate image PROMPT     Stable Diffusion image
/generate video PROMPT     ComfyUI video
/sd [image|video|stop|start] SD mode control

# Services
/services                  Health status
/services start            docker compose up -d
/services stop             docker compose down
/services reset [NAME|all] Wipe and redeploy

# System
/system PROMPT             Set system prompt
/tokens                    Token budget status
/gpu [use]                 GPU info / auto-select model
/mcp                       MCP server status
/index [PATH]              Project indexer
```

## Tool Definitions (line ~242)

```python
TOOLS = [
    {
        "name": "bash_exec",
        "params": {"command": str, "timeout": int},  # timeout default 30
        "confirms": True  # requires user approval
    },
    {
        "name": "read_file",
        "params": {"path": str, "lines": int}  # lines=0 means all
    },
    {
        "name": "write_file",
        "params": {"path": str, "content": str, "append": bool}
    },
    {
        "name": "web_search",
        "params": {"query": str, "count": int}  # count default 5
        "requires": "searxng"
    }
]
```

## Key Functions

### Startup & Config
| Function | Line | Purpose |
|----------|------|---------|
| `main()` | ~3640 | Entry point, argparse, startup flow |
| `load_config()` | ~97 | Load/create %APPDATA%/clod/config.json |
| `save_config()` | ~130 | Persist config changes |
| `_get_clod_root()` | ~150 | Exe-aware root dir resolution |
| `_ensure_local_configs()` | ~175 | Restore config files from bundle/GitHub |
| `_parse_dotenv()` | ~210 | Simple .env parser |
| `_setup_env_wizard()` | ~3500 | First-run .env setup |
| `_check_service_health()` | ~3530 | HTTP health checks for all services |
| `_compute_features()` | ~3560 | Derive feature flags from health + env |
| `_offer_docker_startup()` | ~3580 | Prompt to start Docker if services down |

### Inference & Streaming
| Function | Line | Purpose |
|----------|------|---------|
| `infer()` | ~490 | Main inference: Ollama or LiteLLM |
| `stream_response()` | ~580 | Streaming output with Rich rendering |
| `pick_adapter()` | ~460 | Route model name to ollama/litellm |

### Model Management
| Function | Line | Purpose |
|----------|------|---------|
| `ollama_local_models()` | ~320 | List installed Ollama models |
| `query_gpu_vram()` | ~340 | nvidia-smi GPU detection |
| `recommend_model_for_vram()` | ~360 | VRAM-tier model recommendation |

### Tool Execution
| Function | Line | Purpose |
|----------|------|---------|
| `execute_tool()` | ~400 | Dispatch tool call to handler |
| `tool_bash_exec()` | ~410 | Shell execution with timeout |
| `tool_read_file()` | ~430 | File reading |
| `tool_write_file()` | ~450 | File writing |
| `tool_web_search()` | ~470 | SearXNG query |

### Services
| Function | Line | Purpose |
|----------|------|---------|
| `_get_service_volumes()` | ~3470 | Parse docker-compose for bind mounts |
| `_reset_service()` | ~3490 | Stop/rm/wipe/redeploy one service |

## Intent Classification (intent.py)

```
Layer 1 — Regex rules (checked first, sub-1ms):
  image_gen:  generate|create|make + image|picture|photo      → 0.95
  image_edit: edit|modify|change   + image|picture            → 0.95
  video_gen:  generate|create|make + video|animation          → 0.95
  vision:     describe|look at     + image|screenshot         → 0.90
  code:       write|implement|debug + function|class|code     → 0.90
  reason:     explain why|analyze|compare                     → 0.85

Layer 2 — ONNX embedding (fallback, <100ms CPU):
  Model:     models/intent/model_quint8_avx2.onnx (all-MiniLM-L6-v2 quantized)
  Tokenizer: models/intent/tokenizer.json
  Centroids: models/intent/route_embeddings.npz
  Intents:   chat, code, reason, vision, image_gen, image_edit, video_gen
```

## Pipelines

```
code_review_pipe.py:
  Stage 1: qwen2.5-coder:14b (local) → Stage 2: claude-sonnet
  Use: code generation, debugging, architecture

reason_review_pipe.py:
  Stage 1: deepseek-r1:14b (local, strips <think> tags) → Stage 2: claude-sonnet
  Use: analysis, planning, research

chat_assist_pipe.py:
  Stage 1: llama3.1:8b (local) → Stage 2: claude-haiku
  Use: general Q&A, writing

claude_review_pipe.py:
  Direct Claude review pipeline
```

## Cloud Model Detection

Prefix-based routing in `pick_adapter()`:

```python
CLOUD_MODEL_PREFIXES = ("claude-", "gpt-", "o1-", "o3-", "gemini-", "groq-", "together-")
# If model starts with any prefix → route to LiteLLM (localhost:4000)
# Otherwise → route to Ollama (localhost:11434)
```

## Docker Services

```yaml
# Core (always)
nginx:          80     # reverse proxy
ollama:         11434  # local LLM inference (GPU)
litellm:        4000   # unified LLM gateway
open-webui:     8081   # chat UI
pipelines:      9099   # two-stage routing
searxng:        8080   # private web search
chroma:         8000   # vector DB

# Profile services (optional)
stable-diffusion: 7860  # profile: image
comfyui:          8188  # profile: video
n8n:              5678  # profile: automation
```

Health check endpoints:
```
ollama:   GET /api/tags
litellm:  GET /health
pipelines: GET /
searxng:  GET /healthz
chroma:   GET /api/v2/heartbeat
```

## Config Locations

```
%APPDATA%\clod\config.json    User preferences (auto-created)
D:\clod\.env                  Docker/service environment
D:\clod\.env.example          Template with all variables documented
D:\clod\docker-compose.yml    Service definitions
D:\clod\litellm\config.yaml   LiteLLM model routing
D:\clod\searxng\settings.yml  SearXNG search config
D:\clod\nginx\nginx.conf      Reverse proxy rules
```

## Config Schema (config.json)

```json
{
  "ollama_url":    "http://localhost:11434",
  "litellm_url":   "http://localhost:4000",
  "litellm_key":   "sk-local-dev",
  "pipelines_url": "http://localhost:9099",
  "chroma_url":    "http://localhost:8000",
  "searxng_url":   "http://localhost:8080",
  "default_model": "qwen2.5-coder:14b",
  "pipeline":      null,
  "enable_tools":  false,
  "token_budget":  100000,
  "auto_model":    false,
  "sd_mode":       "image",
  "mcp_port":      8765
}
```

## Token Budget System

```
TokenBudget class (line ~2617):
  - Tracks cumulative Claude API tokens per session
  - Conversion: characters / 4 = estimated tokens
  - Default budget: 100,000 tokens

Thresholds:
  >= 80%  → yellow warning in REPL header
  >= 95%  → prompt user to switch offline
  == 100% → auto-switch to offline mode

Offline mode: blocks all cloud model calls, uses Ollama only
```

## MCP Server (mcp_server.py)

```
HTTP filesystem server, localhost:8765 (configurable)
Daemon thread, started on user opt-in at REPL startup

Endpoints:
  GET  /list    → JSON array of files in workspace
  GET  /<path>  → file contents (text)
  POST /<path>  → write file (raw body)
  DELETE /<path> → delete file

Security: path traversal prevention, localhost binding only
```

## Test Infrastructure

```
Framework: pytest + coverage
Run: python -m pytest tests/unit/ -q --cov=clod --cov-report=term-missing

Unit tests:     tests/unit/     (498 tests, ~76% coverage)
Integration:    tests/integration/test_subprocess.py (clod.py subprocess)
EXE tests:      tests/integration/test_exe.py (compiled binary, Windows only)

Key fixtures (tests/conftest.py):
  fake_console   — Rich Console mock
  mock_cfg       — config dict with test defaults
  mock_session_state — session state dict

HTTP mocking: `responses` library (import responses as resp_lib)
CI gate: --cov-fail-under=90
```

## Build

```bash
# Install deps
pip install -r requirements.txt pyinstaller

# Download intent model files (required for build)
python models/intent/download_model.py

# Build
python -m PyInstaller clod.spec --noconfirm

# Test
dist\clod.exe --version
```

## VRAM Tiers (recommend_model_for_vram)

```
22+ GB → qwen2.5-coder:32b-instruct-q4_K_M
11+ GB → qwen2.5-coder:14b (default)
9.5+ GB → deepseek-r1:14b
5+ GB  → llama3.1:8b
<5 GB  → llama3.1:8b (CPU offload likely)

Reserved overhead: 2000 MB for CUDA driver
```

## Networks (docker-compose)

```
internal (bridge, internal: true):
  chroma, pipelines, litellm, n8n — no internet access

gateway (bridge):
  litellm → Anthropic/OpenAI/Groq APIs
  searxng → web search

default (bridge):
  nginx ←→ open-webui
  nginx dual-homed on internal + default
```
