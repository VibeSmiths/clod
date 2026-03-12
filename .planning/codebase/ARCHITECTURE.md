# Architecture

**Analysis Date:** 2026-03-10

## Pattern Overview

**Overall:** Modular Local AI CLI with Streaming Inference Loops and Service Management

**Key Characteristics:**
- Single-file CLI core (`clod.py`, 2776 lines) with clear functional separation
- Streaming-first inference architecture supporting multiple adapters (Ollama, LiteLLM, Pipelines)
- Session-state REPL with stateful context (messages, budget, config, features)
- Two-stage pipeline pattern: local Ollama → Claude (via LiteLLM)
- Health-aware service orchestration with auto-restore of Docker configs
- Tool execution loop with streaming event protocol

## Layers

**Adapter Layer (Inference Backends):**
- Purpose: Abstract over multiple inference backends (Ollama, OpenAI-compatible APIs, pipelines)
- Location: `clod.py` lines 1462-1598 (`pick_adapter()`, `stream_ollama()`, `stream_openai_compat()`)
- Contains: Router logic that selects backend based on model name and availability
- Depends on: Configuration (URLs, API keys), Health status
- Used by: `infer()` loop

**Streaming Protocol Layer:**
- Purpose: Unify event streams from different backends into a single protocol
- Location: `clod.py` lines 1475-1598 (generator functions)
- Contains: Event dictionaries with `{"type": ..., "text": ..., "name": ..., "arguments": ...}`
- Emit types: `"token"`, `"tool_call"`, `"done"`, `"error"`
- Depends on: `requests` library for HTTP streaming
- Used by: `infer()`, `stream_and_render()`

**Inference Loop (Core Reasoning):**
- Purpose: Multi-turn reasoning with tool execution and budget tracking
- Location: `clod.py` lines 1991-2073 (`infer()` function)
- Contains: Message routing, tool dispatch, token budget updates, offline fallback
- Loop: Infer → stream & render → [if tool calls] → execute tools → add tool results → repeat (max 10 rounds)
- Depends on: Adapter layer, Token budget, Session state
- Used by: REPL and one-shot modes

**Tool Execution Layer:**
- Purpose: Execute user-requested operations (bash, file I/O, web search)
- Location: `clod.py` lines 160-400 (tool definitions and `execute_tool()`)
- Contains: 4 tools (bash_exec, read_file, write_file, web_search)
- Disabled in: Cloud model inference (tools only work with Ollama)
- Depends on: Requests library, subprocess, filesystem
- Used by: `infer()` loop when tool calls received

**Session State Management:**
- Purpose: Maintain user interaction state across REPL turns
- Location: `clod.py` lines 2537-2639 (`run_repl()` function)
- Contains: Current model, pipeline, system prompt, messages, budget, config, features, health
- Mutations: Handle by `/` commands and inference updates
- Depends on: Configuration, health checks
- Used by: REPL loop, slash command handlers

**Command Router (Slash Commands):**
- Purpose: Parse and execute REPL user commands (model switch, pipeline toggle, services, etc.)
- Location: `clod.py` lines 2079-2536 (`handle_slash()` function)
- Contains: 15+ slash commands: `/model`, `/pipeline`, `/tools`, `/offline`, `/tokens`, `/system`, `/clear`, `/save`, `/index`, `/gpu`, `/mcp`, `/sd`, `/services`, `/help`, `/exit`
- Depends on: Session state, configuration, health checks
- Used by: `run_repl()` main loop

**Configuration & Persistence:**
- Purpose: Load/save user settings and manage environment variables
- Location: `clod.py` lines 239-290, 633-678 (config I/O and .env parsing)
- Contains: Default config dict, user JSON file merging, dotenv parsing
- Paths: `~/.config/clod/config.json` (Linux/Mac) or `%APPDATA%/clod/config.json` (Windows)
- Depends on: Filesystem
- Used by: `main()`, throughout

**Service Health & Initialization:**
- Purpose: Check Docker service availability and restore missing configs
- Location: `clod.py` lines 678-952, 825-859 (startup wizard, health checks, config restore)
- Contains: HTTP health checks for Ollama, LiteLLM, Pipelines, SearXNG, ChromaDB
- Features computed: Cloud models available, web search available, offline-only fallback
- Depends on: Docker Compose, config files, requests library
- Used by: `main()` before REPL entry

**Rich UI & Rendering:**
- Purpose: Render markdown, panels, progress indicators, status messages
- Location: `clod.py` lines 1873-1985 (UI helpers and `stream_and_render()`)
- Contains: `Console` singleton, markdown rendering, live spinner, panel builders
- Depends on: Rich library
- Used by: `infer()`, `handle_slash()`, throughout

**Project Indexer:**
- Purpose: Auto-generate CLAUDE.md and README.md for indexed projects
- Location: `clod.py` lines 1601-1812 (`run_index_mode()` and helpers)
- Contains: Project type detection, context gathering, AI-driven documentation generation
- Depends on: `_gather_context()`, cloud models (Claude)
- Used by: `main()` when `--index` flag provided

**Token Budget Tracker:**
- Purpose: Track cumulative Claude API token usage across session
- Location: `clod.py` lines 1817-1868 (`TokenBudget` class and threshold checker)
- Contains: Budget allocation, usage tracking (char/4 approximation), thresholds (warn 80%, offer 95%, force 100%)
- Depends on: Message content
- Used by: `infer()` loop, REPL state display

**MCP Filesystem Server:**
- Purpose: Expose project filesystem to Claude via HTTP-based file operations
- Location: `mcp_server.py` (109 lines) - separate service
- Contains: HTTP handler (GET list/read, POST write, DELETE), path traversal protection
- Runs on: Port 8765 by default (daemon thread during REPL)
- Depends on: Python stdlib http.server
- Used by: REPL when user enables MCP access

## Data Flow

**REPL Session Initialization:**

1. `main()` loads config (or creates it)
2. Restore missing Docker configs and .env from GitHub/bundle
3. Run env setup wizard if first-run (interactive)
4. Check service health (HTTP pings to Ollama, LiteLLM, etc.)
5. Compute feature flags (cloud_models, web_search, offline_default)
6. Offer docker startup if services missing
7. Enter `run_repl()`, prompt for MCP access if TTY
8. Start MCP server in daemon thread
9. Print header, show banner
10. Loop: prompt user → handle `/` commands or → `infer()` → update messages → check token budget

**Message-Driven Inference Turn:**

1. User submits message (REPL) or CLI provides prompt (one-shot/pipe)
2. Append `{"role": "user", "content": message}` to messages list
3. Call `infer(messages, model, pipeline, cfg, tools_on, offline, budget, session_state)`
4. `infer()` selects adapter via `pick_adapter()`
5. If offline or cloud model unavailable → redirect to local model
6. Call streaming function (`stream_ollama()` or `stream_openai_compat()`)
7. Stream yields events; collect in `stream_and_render()`
8. Display tokens live, accumulate in `final_content`
9. If tool calls in response → loop up to 10 rounds:
   - Print tool call (name + args)
   - `execute_tool()` runs the tool (bash/file/web)
   - Print tool result (500-char preview)
   - Add to messages: `{"role": "tool", "name": ..., "content": result}`
   - Call adapter again with extended messages
10. Update budget if Claude model used
11. Return final assistant message, append to session messages

**State Mutation via Slash Commands:**

1. User types `/model llama3.1:8b` (or other command)
2. `handle_slash()` parses verb + args
3. Update `session_state` dict in place (model, pipeline, tools_on, offline, etc.)
4. May trigger side effects:
   - `/model` → warmup Ollama if local model
   - `/gpu` → query VRAM, recommend model
   - `/mcp` → toggle MCP server
   - `/sd` → switch SD mode or restart container
   - `/services` → health check or docker restart
   - `/save` → write conversation JSON to disk
5. Return to REPL, continue with updated state

**State Management:**

**Session-Level State:**
- `session_state` dict in `run_repl()` contains: model, pipeline, tools_on, system, offline, cfg, budget, sd_mode, mcp_httpd, mcp_dir, features, health
- Persisted across turns (messages accumulate in `messages` list)
- Token budget cumulative across session

**Config-Level Persistence:**
- `load_config()` reads from JSON file at startup
- `save_config()` writes user overrides
- Environment variables from .env file (parsed via `_parse_dotenv()`)
- Ollama/LiteLLM URLs, API keys, default model stored here

**Runtime Transient State:**
- Messages list (in-memory, session lifetime)
- MCP server process (daemon thread)
- Health dict (computed once at startup, may be rechecked via `/services`)

## Key Abstractions

**Adapter Pattern (Backend Selection):**
- Purpose: Abstract inference backend selection and streaming
- Examples: `pick_adapter()` returns `"ollama"` | `"litellm"` | `"pipeline"` | `"cloud_unavailable"`
- Pattern: Return string enum, caller uses if/elif to dispatch to correct streaming function

**Pipeline Abstraction:**
- Purpose: Two-stage inference without modifying main `infer()` loop
- Pattern: Pipeline name becomes a pseudo-model; OpenAPI-compat streaming at `cfg["pipelines_url"]`
- Examples in `pipelines/`: code_review_pipe.py, reason_review_pipe.py, chat_assist_pipe.py
- Each defines `Valves` config (model choices), `pipe()` async method (stream protocol)

**Tool Definition Protocol:**
- Purpose: Standardize tool description and argument passing
- Format: List of dicts with `type="function"`, `function={name, description, parameters}`
- Execution: Tool name routed to handler (bash_exec, read_file, write_file, web_search)
- Only enabled: With Ollama adapter and tools_on=True

**Event Stream Protocol:**
- Purpose: Unify different backend streaming responses
- Format: Generator yielding dicts `{"type": ..., "text": ..., "name": ..., "arguments": ...}`
- Types: token (streamed), tool_call (for tool dispatch), done (final message), error (on failure)
- Consumers: `stream_and_render()`, `infer()` loop

**Feature Flags:**
- Purpose: Gate optional capabilities based on service availability
- Computed in: `_compute_features(env_vars, health)`
- Flags: `cloud_models`, `web_search`, `offline_default`, `services_running`
- Used by: `pick_adapter()`, `infer()`, slash commands

## Entry Points

**Interactive REPL:**
- Location: `clod.py` main line (no args, TTY stdin)
- Triggers: User runs `clod` with no flags
- Responsibilities: Initialization (config restore, health checks), prompt MCP access, run REPL loop

**One-Shot Mode:**
- Location: `clod.py` main → `run_oneshot()`
- Triggers: User runs `clod -p "prompt"`
- Responsibilities: Single inference turn, exit (no budget tracking, no tool loop)

**Pipe Mode:**
- Location: `clod.py` main, detects stdin not TTY
- Triggers: User runs `echo "prompt" | clod`
- Responsibilities: Read stdin, single inference, exit

**Index Mode:**
- Location: `clod.py` main → `run_index_mode()`
- Triggers: User runs `clod --index [path]`
- Responsibilities: Detect project types, gather context, generate CLAUDE.md, update README

**MCP Filesystem Server:**
- Location: `mcp_server.py start()` function
- Triggers: Started in daemon thread during REPL if user consents
- Responsibilities: HTTP server on port 8765 (configurable), file operations (list, read, write, delete)

## Error Handling

**Strategy:** Graceful degradation with user-facing warnings

**Patterns:**

**Inference Failures:**
- Ollama unreachable → yield error event → display red error banner → return empty string
- LiteLLM unreachable → display yellow panel "⚠ Cloud Unavailable" → fall back to local model
- Model pull failure → return error message in chat

**Service Health Failures:**
- Missing service → offer interactive docker startup via `_offer_docker_startup()`
- If user declines → compute features with degraded capabilities (no cloud, no web search)

**Configuration Errors:**
- Missing .env on first run → run `_setup_env_wizard()` interactively, prompt for each key
- Malformed config.json → `load_config()` merges over defaults, missing keys get defaults
- Invalid docker-compose.yml → restore from GitHub or bundle via `_ensure_local_configs()`

**Tool Execution:**
- Bash timeout (30s) → return error message
- File not found → return error message from `tool_read_file()`
- Web search connection → return error in results panel

**Token Budget:**
- At 80% → print yellow warning
- At 95% → prompt user "Go offline?" (can decline)
- At 100% → auto-switch to offline mode (local model only)

## Cross-Cutting Concerns

**Logging:** None. Uses `console.print()` for interactive output only (Rich UI).

**Validation:**
- Config keys: Defaults provided, user values merged, type not validated
- Tool args: Passed directly from LLM to handler (trust LLM correctness)
- MCP paths: `_safe_path()` prevents directory traversal

**Authentication:**
- Ollama: No auth (localhost)
- LiteLLM: API key from `cfg["litellm_key"]` (default "sk-local-dev")
- Pipelines: Same key as LiteLLM
- SearXNG: No auth (localhost)

**Threading:**
- MCP server runs in daemon thread via `threading.Thread(..., daemon=True)`
- REPL remains single-threaded (main thread)
- No locks needed (no shared mutable state across threads)

**Platform Differences:**
- Config path: Windows `%APPDATA%\clod\`, Unix `~/.config/clod/`
- TTY detection: `sys.stdin.isatty()`, `sys.stdout.isatty()` (skips MCP, env wizard on non-TTY)
- Executable root: PyInstaller frozen → `sys.executable.parent`, dev → `__file__.parent`

---

*Architecture analysis: 2026-03-10*
