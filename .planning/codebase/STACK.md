# Technology Stack

**Analysis Date:** 2026-03-10

## Languages

**Primary:**
- Python 3.11 - Main CLI application (`clod.py`), ~1900 lines
- YAML - Docker Compose and configuration files (`docker-compose.yml`, `litellm/config.yaml`, `searxng/settings.yml`)

**Secondary:**
- HTML/JavaScript - Open-WebUI web interface (container-based)
- Bash - Pre-commit hooks, shell script execution

## Runtime

**Environment:**
- Python 3.11 (pinned in `pyproject.toml` target-version, CI/CD, and PyInstaller spec)
- Docker/Docker Compose (orchestration of 10+ containerized services)

**Package Manager:**
- pip (Python dependencies)
- Lockfile: No lockfile (pinned versions in `requirements.txt`)
- Docker for containerized service dependencies

## Frameworks

**Core:**
- `rich` 13.0.0+ - Terminal UI (panels, markdown, live displays, formatting)
- `prompt_toolkit` 3.0.0+ - Interactive REPL with history and syntax highlighting
- `requests` 2.31.0+ - HTTP client for all service communication
- `psutil` 5.9.0+ - Optional GPU/VRAM introspection (graceful fallback if missing)

**CLI/Async:**
- `argparse` (stdlib) - Command-line argument parsing
- `http.server` (stdlib) - MCP filesystem server (`mcp_server.py`, port 8765)

**Testing:**
- `pytest` - Test runner (`tests/unit/`, `tests/integration/`)
- `pytest-cov` - Coverage measurement
- `responses` - HTTP mocking for requests library
- Rich fixtures for console testing

**Build/Dev:**
- `PyInstaller` - Windows EXE bundling (`clod.spec`)
  - Bundles `docker-compose.yml`, config directories, `.env.example`
  - Runtime hook for rich unicode support
- `black` 25.1.0 - Code formatting (100 char line length)
- `pylint` - Linting (fail-under 7.0, excludes C01xx W0212 R0903)
- `bandit[toml]` - Security scanning (skips subprocess/shell intentionally)
- `pip-audit` - Dependency CVE scanning

## Key Dependencies

**Critical:**
- `requests` - HTTP communication with all 5 services (ollama, litellm, pipelines, searxng, chroma)
- `rich` - All terminal output, markdown rendering, live progress
- `prompt_toolkit` - Interactive REPL, command history at `~/.clod_history`

**Infrastructure:**
- Docker Compose services (10 containers + optional profiles):
  - `ollama/ollama` / `ollama/ollama:rocm` / CPU variant - Local LLM inference
  - `ghcr.io/berriai/litellm:main-latest` - Unified LLM gateway (Anthropic, OpenAI, Groq, Gemini, Together)
  - `ghcr.io/open-webui/open-webui:main` - Web UI for chat interface
  - `ghcr.io/open-webui/pipelines:main` - Multi-LLM routing pipelines
  - `searxng/searxng:latest` - Private meta search engine
  - `chromadb/chroma:latest` - Vector database for embeddings
  - `nginx:alpine` - Reverse proxy (path-based routing)
  - `ghcr.io/xander-rudolph/stable-diffusion:latest` (profile: image) - AUTOMATIC1111 image generation
  - `yanwk/comfyui-boot:cu128-slim` (profile: video) - ComfyUI video generation
  - `ghcr.io/matatonic/openedai-speech` (profile: audio) - TTS (text-to-speech)
  - `n8nio/n8n:latest` (profile: automation) - Automation workflows

## Configuration

**Environment:**
- `.env` file (not tracked, created from `.env.example`)
- Environment variables define:
  - Service ports (OPEN_WEBUI_PORT, OLLAMA_PORT, etc.)
  - Data storage paths (BASE_DIR, OLLAMA_DATA_DIR, etc.)
  - API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
  - Service parameters (OLLAMA_GPU_OVERHEAD, OLLAMA_KEEP_ALIVE, OLLAMA_MAX_LOADED_MODELS)
  - Feature flags (ENABLE_IMAGE_GENERATION, ENABLE_RAG_WEB_SEARCH, etc.)

**Build:**
- `pyproject.toml` - Python project metadata and tool configs:
  - Black: 100 char line length, Python 3.11
  - Pylint: fail-under 7.0, disabled C01xx docstrings + W0212 + R0903
  - Bandit: excludes tests, B404/B602/B605 intentional (subprocess execution)
  - Pytest: testpaths=["tests"], short tracebacks
  - Coverage: source=["clod"], omit tests/scripts/rthooks
- `clod.spec` - PyInstaller specification:
  - Bundles docker-compose.yml, config files, .env.example in executable
  - Rich unicode data as separate files (not frozen modules)
  - Icon: `assets/icon.ico`
- `.pre-commit-config.yaml` - Pre-commit hook:
  - `black` v25.1.0 with 100 char line length

**Service Configuration:**
- `docker-compose.yml` - 420+ lines defining all services, networks, volumes
  - `internal` network (isolated, no internet)
  - `gateway` network (internet-capable for API calls)
  - Bind-mount volumes for data persistence
- `litellm/config.yaml` - Model routing config for 15+ models (Claude, GPT-4o, Groq, Gemini, Together, Ollama local)
- `nginx/nginx.conf` - Reverse proxy configuration
- `searxng/settings.yml` - Meta search engine configuration
- `pipelines/` - Multi-LLM pipeline definitions (code_review, reason_review, chat_assist, claude_review)

## Platform Requirements

**Development:**
- Python 3.11+
- Docker / Docker Compose 2.0+
- For Windows: PyInstaller (one-file EXE generation)
- GPU (optional but recommended): NVIDIA (or AMD ROCm variant) for Ollama/SD
- Minimum RAM: 8 GB (recommended 16+ GB for 14b models)
- Disk: ~100 GB for model storage (cached in `${BASE_DIR}/ollama/data`)

**Production:**
- Deployment target: Docker containerized (Linux host recommended)
- Cloud APIs optional: Anthropic, OpenAI, Groq, Gemini, Together (via LiteLLM)
- All data stored locally in host bind-mounts (no external DB required)

## Model Pinning

**Local Models (Ollama):**
- Default: `qwen2.5-coder:32b-instruct-q4_K_M` (20 GB VRAM)
- Fallbacks: `qwen2.5-coder:14b` (10 GB), `deepseek-r1:14b` (9 GB), `llama3.1:8b` (5 GB)
- Vision: `qwen2.5vl:7b`

**Cloud Models (LiteLLM routing):**
- Anthropic: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5-20251001
- OpenAI: gpt-4o, o3-mini
- Groq: llama-3.3-70b-versatile, llama-3.2-90b-vision-preview
- Google: gemini-2.0-flash, gemini-2.0-pro-exp
- Together: meta-llama/Llama-3.3-70B-Instruct-Turbo, deepseek-ai/DeepSeek-V3

## CI/CD Infrastructure

**Platform:** GitHub Actions (`.github/workflows/pipeline.yml`)

**Stages:**
1. `versioner` - Determines version (PR number, manual override, or auto-increment)
2. `lint` - Black, Pylint, Bandit, pip-audit (security checks)
3. `unit-tests` - Pytest with coverage reporting (76% target)
4. `build-windows` - PyInstaller EXE (Windows runner)
5. `build-linux` - PyInstaller AppImage (Linux runner)
6. `integration-tests` - Windows/Linux subprocess tests (non-PR runs)
7. `exe-tests` - Integration tests against compiled binary (Windows)
8. `release` - Gated on both integration + exe tests (contains release logic)

**Test Coverage:** 307 unit tests, ~76% code coverage, coverage reports posted to PRs

---

*Stack analysis: 2026-03-10*
