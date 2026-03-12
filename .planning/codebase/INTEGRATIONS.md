# External Integrations

**Analysis Date:** 2026-03-10

## APIs & External Services

**Cloud LLM Providers (via LiteLLM proxy):**
- **Anthropic** - Claude API for cloud inference
  - SDK/Client: LiteLLM (wrapper) + requests for HTTP
  - Auth: `ANTHROPIC_API_KEY` (env var, injected into LiteLLM container)
  - Endpoint: `litellm/config.yaml` routes claude-opus, claude-sonnet, claude-haiku to api.anthropic.com
  - Models: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001

- **OpenAI** - GPT and o-series models
  - SDK/Client: LiteLLM
  - Auth: `OPENAI_API_KEY`
  - Endpoint: api.openai.com (proxied through LiteLLM)
  - Models: gpt-4o, o3-mini

- **Groq** - Open-source model inference (free tier available)
  - SDK/Client: LiteLLM
  - Auth: `GROQ_API_KEY`
  - Endpoint: api.groq.com (via LiteLLM)
  - Models: llama-3.3-70b-versatile, llama-3.2-90b-vision-preview

- **Google Gemini** - Gemini model family
  - SDK/Client: LiteLLM
  - Auth: `GEMINI_API_KEY`
  - Endpoint: generativelanguage.googleapis.com (via LiteLLM)
  - Models: gemini-2.0-flash, gemini-2.0-pro-exp

- **Together AI** - Open-source model hosting
  - SDK/Client: LiteLLM
  - Auth: `TOGETHER_API_KEY`
  - Endpoint: api.together.xyz (via LiteLLM)
  - Models: meta-llama/Llama-3.3-70B-Instruct-Turbo, deepseek-ai/DeepSeek-V3

**Search Engine Integration:**
- **SearXNG** - Private meta search (aggregates external search engines)
  - Service: `searxng` Docker container (localhost:8080)
  - Usage: `/tools` command enables web search via `tool_web_search()` in `clod.py:357`
  - Endpoint: `http://localhost:8080/search?q=<query>&format=json`
  - Health check: `http://localhost:8080/healthz`
  - No auth required (internal Docker network)
  - Configuration: `searxng/settings.yml` (defines trusted networks, API settings)

**Image Generation:**
- **Stable Diffusion (AUTOMATIC1111)** - Image generation backend
  - Service: `stable-diffusion` Docker container (localhost:7860, profile: image)
  - SDK/Client: Direct HTTP (requests library)
  - Endpoint: `http://localhost:7860` (simple health check)
  - Auth: Optional `AUTOMATIC1111_API_AUTH` env var
  - Configuration in Open-WebUI: image model, CFG scale, sampler, scheduler
  - Function: `sd_check()` in `clod.py:568`
  - No direct API calls from clod.py; accessed via Open-WebUI UI

- **ComfyUI** - Node-based Stable Diffusion (video generation)
  - Service: `comfyui` Docker container (localhost:8188, profile: video)
  - SDK/Client: Direct HTTP (requests library)
  - Endpoint: `http://localhost:8188`
  - Health check: `comfyui_check()` in `clod.py:625`
  - Configuration: `COMFYUI_IMAGE`, `COMFYUI_HOST`, `COMFYUI_PORT` in `.env`
  - No direct API calls from clod.py; accessed via Open-WebUI UI

**Text-to-Speech:**
- **OpenAI TTS API** - Via local OpenEdAI Speech container
  - Service: `tts` Docker container (localhost:8000, optional)
  - Used by: Open-WebUI for audio generation
  - Endpoint: `http://localhost:8000/v1` (OpenAI-compatible API)
  - Auth: Custom API key (`TTS_PORT` and `TTS_HOST` combined)
  - Configuration: model=tts-1-hd, voice customizable via `TTS_VOICE`

## Data Storage

**Databases:**
- **ChromaDB** - Vector database for embeddings
  - Service: `chroma` Docker container (localhost:8000)
  - Type: Vector/semantic search
  - Client: Open-WebUI REST API
  - Connection: `http://localhost:8000/api/v2/heartbeat` (health endpoint)
  - Storage: Host bind-mount at `${CHROMA_DATA}` (e.g., `~/docker-dependencies/chroma/data`)
  - Used by: Open-WebUI RAG (retrieval-augmented generation)

**File Storage:**
- **Local filesystem only** - All data stored in host bind-mounts
  - Ollama models: `${OLLAMA_DATA_DIR}` (hundreds of GB)
  - Open-WebUI data: `${OWUI_DATA_DIR}` (user chats, settings)
  - Stable Diffusion outputs: `${SD_OUTPUT_DIR}`, models: `${SD_CKPT_MODELS_DIR}`, `${SD_LORA_MODELS_DIR}`
  - Pipelines data: `${PIPELINES_DATA}`
  - n8n data: `${N8N_DATA}` (profile: automation)
  - ComfyUI: `${COMFYUI_MODELS_DIR}`, `${COMFYUI_OUTPUT_DIR}`, `${COMFYUI_CUSTOM_NODES_DIR}`
  - SearXNG: `${SEARXNG_CONFIG_DIR}` + `${SEARCH_DIR}` (cache)
  - TTS: `${VOICES_DIR}`, `${TTS_CONFIG_DIR}`
  - Nginx: `${NGINX_DATA_DIR}`, `${LE_DATA_DIR}` (Let's Encrypt)

**Caching:**
- **LiteLLM local cache** - Reduces cost/latency on repeated queries
  - Type: local (in-memory + disk)
  - TTL: 3600 seconds (1 hour)
  - Configuration: `litellm/config.yaml` lines 90-95
  - Fallback chain: claude-opus → gpt-4o → groq-fast → local-32b

**Model Cache:**
- **Ollama model cache** - Loaded models kept in VRAM
  - Unload after: `OLLAMA_KEEP_ALIVE=5m` (configurable)
  - Max concurrent models: `OLLAMA_MAX_LOADED_MODELS=1` (prevents multi-model VRAM pressure)
  - GPU overhead reserved: `OLLAMA_GPU_OVERHEAD=536870912` (512 MB, avoids OOM)

## Authentication & Identity

**Auth Provider:**
- **Internal (LiteLLM master key)** - Service-to-service auth
  - Key: `LITELLM_MASTER_KEY` (env var, defaults to `sk-local-dev`)
  - Used by: `clod.py` and Pipelines to authenticate to LiteLLM
  - Stored in: `.env` (not tracked, user-configured)
  - Also used in Open-WebUI (`OPENAI_API_KEY` set to master key for local routing)

- **Optional OAuth (Microsoft)** - Enterprise Open-WebUI auth
  - Provider: Microsoft Entra/Azure AD
  - Configuration: `ENABLE_OAUTH_SIGNUP`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_CLIENT_TENANT_ID`
  - Not enabled by default

- **No authentication** for local services:
  - Ollama API: unauthenticated (localhost-only)
  - Pipelines: authenticated via LiteLLM master key header
  - Chroma: unauthenticated (internal network only)
  - SearXNG: unauthenticated (internal network only)

## Monitoring & Observability

**Error Tracking:**
- None configured (no Sentry, Datadog, etc.)

**Logs:**
- **Docker logging**: JSON-file driver with rotation (5 MB max-size, 2 file rotation)
  - Services configured: ollama, litellm, searxng, stable-diffusion, comfyui, tts
- **Rich console output**: Terminal UI logs all operations in `clod.py`
- **No centralized logging** (logs stay in container volumes)

**Health Checks:**
- Proactive service health monitoring in `_check_service_health()` (`clod.py:827`)
- Endpoints checked:
  - `ollama`: `http://localhost:11434/api/tags` (list models)
  - `litellm`: `http://localhost:4000/health` (LiteLLM health)
  - `pipelines`: `http://localhost:9099/` (Pipelines root)
  - `searxng`: `http://localhost:8080/healthz` (SearXNG health)
  - `chroma`: `http://localhost:8000/api/v2/heartbeat` (ChromaDB heartbeat)
- Health results cached in session for feature flags (cloud_models, web_search, etc.)

## CI/CD & Deployment

**Hosting:**
- Local (Docker Compose on user's machine)
- Optional cloud: Only for API keys (Anthropic, OpenAI, etc.) — actual inference local

**CI Pipeline:**
- GitHub Actions (`.github/workflows/pipeline.yml`)
- Stages: lint → unit-tests → build-windows/build-linux → integration-tests → release
- Security scanning: Bandit (MEDIUM+), pip-audit for CVEs
- Coverage: pytest-cov with codecov reporting

**Build Artifacts:**
- Windows: `dist/clod.exe` (PyInstaller one-file executable)
- Linux: AppImage with Python 3.11 + all dependencies embedded
- Release: GitHub Releases (artifacts retained 30 days, PR artifacts 7 days)

## Environment Configuration

**Required env vars (for cloud models):**
- `ANTHROPIC_API_KEY` - Anthropic Claude API key
- `OPENAI_API_KEY` - OpenAI GPT API key
- `GROQ_API_KEY` - Groq API key
- `GEMINI_API_KEY` - Google Gemini API key
- `TOGETHER_API_KEY` - Together AI API key
- `LITELLM_MASTER_KEY` - Internal service auth (can be arbitrary, defaults safe)

**Optional env vars:**
- `OLLAMA_IMAGE` - Docker image variant (default: ollama/ollama, rocm variant available)
- `HF_TOKEN` - HuggingFace token for gated models
- `MICROSOFT_CLIENT_*` - Microsoft OAuth credentials
- GPU configuration: `NVIDIA_VISIBLE_DEVICES`, `NVIDIA_DRIVER_CAPABILITIES`
- Ports: `OPEN_WEBUI_PORT`, `OLLAMA_PORT`, `LITELLM_PORT`, `PIPELINES_PORT`, `SEARXNG_PORT`, etc.

**Secrets location:**
- `.env` file (user-created from `.env.example`, never committed)
- Injected into Docker containers via environment variables
- Never logged or exposed (LiteLLM `drop_params: true`)

**Default Configuration File:**
- `.env.example` - Template bundled in PyInstaller exe
- On first run, interactive wizard (`_setup_env_wizard()`) prompts for API keys and copies example to `.env`

## Webhooks & Callbacks

**Incoming:**
- None (clod is a command-line tool, no webhook endpoints)

**Outgoing:**
- None to external services (all integration is pull-based via HTTP GET/POST)

## MCP Filesystem Server

**Local Service:**
- Custom HTTP server in `mcp_server.py` (port 8765, localhost-only)
- Implements Model Context Protocol (MCP) filesystem interface
- Endpoints:
  - `GET /list` - List files in served directory
  - `GET /<file>` - Read file
  - `POST /<file>` - Write file (raw body as content)
  - `DELETE /<file>` - Delete file
- Started on-demand by `start_mcp_server()` in `clod.py:1349`
- Used by: Open-WebUI Pipelines to access workspace (mounted at `/workspace`)
- Example workspace dir: `./shared` or user-specified via `--mcp-dir`

## GitHub Integration

**Configuration Source:**
- Base URL: `https://raw.githubusercontent.com/VibeSmiths/clod/main`
- Used for: Auto-restoring config files on first run (if offline detection fails)
- Path examples: `litellm/config.yaml`, `searxng/settings.yml`, `nginx/nginx.conf`
- Fallback: If GitHub unreachable, bundled configs in exe are used

---

*Integration audit: 2026-03-10*
