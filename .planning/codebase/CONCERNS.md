# Codebase Concerns

**Analysis Date:** 2026-03-10

## Tech Debt

**Monolithic Main Module (clod.py):**
- Issue: Core file is 2,776 lines in a single module, mixing CLI entry points, streaming logic, tool execution, slash commands, REPL, service health checks, and MCP server management.
- Files: `clod.py` (lines 1–2776)
- Impact: Difficult to test interactively; high cognitive load for modifications; circular dependencies between functions; state mutations scattered across session_state dict; slash command handlers duplicate logic.
- Fix approach: Extract into submodules: `clod/repl.py` (run_repl, handle_slash, infer), `clod/services.py` (health checks, docker compose), `clod/tools.py` (tool definitions and execution), `clod/inference.py` (stream_ollama, stream_openai_compat, pick_adapter).

**Abandoned Pipeline Experiments:**
- Issue: `/d/clod/pipelines/failed/` contains 4 old pipeline implementations that are no longer used (base_two_stage_pipe.py, chat_assist_pipe.py, code_review_pipe.py, reason_review_pipe.py).
- Files: `pipelines/failed/*.py`
- Impact: Code clutter; maintenance burden; unclear what was attempted and why it failed; no docstrings explaining rationale.
- Fix approach: Move to git history (git log) or delete with clear commit message explaining each failure. Document lessons learned in CLAUDE.md.

**Broad Exception Handling Without Logging:**
- Issue: ~70+ `except Exception:` clauses silently swallow errors with minimal or no logging (e.g., lines 275–276, 406, 499, 525, 563, 572, 591–592, 620, 629, 650, 839, 1109–1110, 1709).
- Files: `clod.py` (throughout)
- Impact: Silent failures; difficult to debug integration issues; tool failures not reported; missing context for why requests fail (network, timeout, malformed response).
- Fix approach: Use a centralized logger (e.g., `logging` module); log with context (URL, model name, service name, timeout). Replace bare `except Exception:` with specific exception types (`requests.ConnectionError`, `requests.Timeout`, `json.JSONDecodeError`, etc.). Log at WARNING or ERROR level with traceback if appropriate.

**Untestable REPL and Interactive Code:**
- Issue: run_repl() function (lines 2537–2638) and main() CLI path (lines 1854–1866 token budget prompts, 2765–2772) require interactive TTY and prompt_toolkit, making unit testing infeasible.
- Files: `clod.py` (run_repl lines 2537–2638, main lines 2659–2772, handle_slash lines 2079–2515, check_token_thresholds lines 1846–1868)
- Impact: ~6% of codebase has zero coverage; critical user-facing features untested (token budget warnings, offline mode toggle, slash command handling); regressions in REPL logic only caught at integration test time.
- Fix approach: Extract pure logic into testable functions: e.g., `compute_token_action(fraction: float) -> str` returns action without printing; separate prompt generation from input handling; mock PromptSession in unit tests. Keep interactive glue in run_repl() but keep it thin.

## Known Bugs

**Broken SD/nginx Path (README documented):**
- Symptoms: Stable Diffusion web assets fail to load via `/sd/` nginx path; users must use direct localhost:7860 port.
- Files: `README.md` (line 62), `docker-compose.yml` (nginx routing likely), `nginx/nginx.conf` (SD routing rules).
- Current workaround: Use direct SD port (localhost:7860 for AUTOMATIC1111, localhost:8188 for ComfyUI); nginx `/sd/` path serves only as reverse proxy without full asset support.
- Fix approach: Add nginx rewrite rules or proxy pass filters to rewrite asset paths in SD responses. Verify Open-WebUI SD mode switch logic doesn't depend on nginx path working.

## Error Handling & Robustness

**Missing Retry Logic for Transient Failures:**
- Issue: All HTTP requests (ollama_pull, stream_ollama, health checks, file downloads from GitHub) use single-shot requests with no exponential backoff or retry on transient errors (network timeouts, 503).
- Files: `clod.py` (lines 304–310 bash_exec subprocess, 426–438 ollama_pull, 489–498 stream_ollama, 784–792 GitHub fetch, 837–840 health checks, 1497–1508 stream_openai_compat).
- Impact: Network blips or temporary service unavailability causes tool failures; users must manually retry; pulling large models from Ollama can fail on slow networks.
- Fix approach: Implement `retry_with_backoff(fn, max_retries=3, backoff_base=1.0)` wrapper using `time.sleep()` with exponential backoff; use for Ollama API, LiteLLM, GitHub config fetches. Set sane timeout values (e.g., pull timeout 3600s but with intermediate stream events to avoid looking hung).

**Incomplete Exception Context in Tool Execution:**
- Issue: tool_bash_exec (lines 290–322) catches TimeoutExpired and generic Exception separately but returns string error messages; other tools (file_read, file_write, tool_web_search) also catch broad Exception blocks without logging command/model context.
- Files: `clod.py` (tool_bash_exec lines 290–322, tool_file_read lines 330–340, tool_file_write lines 344–355, tool_web_search lines 358–382, execute_tool lines 384–391).
- Impact: When a tool fails, session_state is not updated to track which tool failed; retry logic at inference level (lines 2038–2073) has no context about which tool caused an error.
- Fix approach: Raise custom exceptions (`ToolError(name, args, original_exception)`) instead of swallowing; wrap infer() in try/except that catches ToolError and logs with context; add tool failure count to session_state.

## Security Considerations

**Unvalidated Shell Command Execution:**
- Risk: tool_bash_exec (lines 290–322) accepts arbitrary shell commands from LLM and executes with `shell=True` after user confirmation prompt.
- Files: `clod.py` (lines 290–322, tool definition lines 164–175).
- Current mitigation: Interactive confirmation prompt; runs as local user (no privilege escalation).
- Recommendations:
  1. Add command parsing/validation: reject commands with shell metacharacters (`;`, `|`, `>`, `&`, `$()`, backticks) that aren't in a whitelist.
  2. Log all executed commands (even confirmed ones) with timestamp for audit trail.
  3. Consider restricting bash_exec to a sandbox (chroot, containers, or subprocess with restrictive file descriptor limits).
  4. Add rate-limiting: max N commands per session to prevent runaway loops.

**Environment Variables Loaded Without Validation:**
- Risk: .env file and Docker compose environment variables (ANTHROPIC_API_KEY, OPENAI_API_KEY, LITELLM_MASTER_KEY, etc.) are loaded via _parse_dotenv (lines 634–671) and passed directly to LiteLLM and service startup.
- Files: `clod.py` (_parse_dotenv lines 634–671, main lines 2673–2675, _compute_features lines 900–932).
- Current mitigation: .env file loaded from local disk only; not committed to git; permissions depend on filesystem ACLs.
- Recommendations:
  1. Validate .env keys before using: check for expected prefixes (ANTHROPIC_, OPENAI_, etc.) and reject unknown keys.
  2. Mask secrets in logs: replace API keys with `***` when logging or printing config.
  3. Add env var encryption at rest (optional, for future hardening).
  4. Document that .env must have restricted permissions (e.g., chmod 600 on Unix).

**MCP Filesystem Server Listens on localhost Only:**
- Risk: mcp_server.py (port 8765, localhost-only) could be accessed by other processes on same machine with elevated privileges; no authentication.
- Files: `mcp_server.py` (start function), `clod.py` (start_mcp_server lines 1348–1357).
- Current mitigation: Bound to localhost (127.0.0.1); no firewall bypass; typical development machine is single-user.
- Recommendations:
  1. Add Bearer token auth: require Authorization header for MCP requests.
  2. Use Unix socket instead of TCP (if not on Windows) to avoid network stack.
  3. Document that MCP is development-only and should not be exposed to untrusted networks.

## Performance Bottlenecks

**Token Budget Math Uses Approximate Char-to-Token Ratio:**
- Problem: TokenBudget.add() (lines 1824–1828) divides char count by 4 to estimate tokens; actual token count varies per model and encoding.
- Files: `clod.py` (TokenBudget class lines 1817–1843, add method lines 1824–1828, check_token_thresholds lines 1846–1868).
- Cause: No call to actual tokenizer (e.g., tiktoken, transformers); char/4 is rough heuristic from Claude docs.
- Impact: Token budget warnings/limits may trigger early (overestimate) or late (underestimate); users may exhaust budget unexpectedly or waste budget threshold.
- Improvement path: Use actual tokenizer for Claude models if available (via LiteLLM or separate tiktoken import); fall back to char/4 if unavailable. Store token estimate in response metadata if LiteLLM provides it.

**Streaming Rendering Blocks on First Event:**
- Problem: stream_and_render() (lines 1960–1985) uses `with console.status()` which blocks all output until first token arrives; large models or slow connections cause perception of hang.
- Files: `clod.py` (stream_and_render lines 1960–1985, infer lines 1991–2073).
- Cause: Rich's console.status spinner waits for first event before rendering; no timeout or early feedback.
- Impact: User sees blank spinner for 5–30 seconds on first inference; appears hung; no feedback on what's happening.
- Improvement path: Move spinner to infer() context; emit a "generating..." message immediately before streaming. Use contextlib.suppress to handle edge case where stream yields nothing.

**No Connection Pooling for Repeated HTTP Requests:**
- Problem: Each HTTP call (to ollama, litellm, searxng, etc.) creates a new requests.Session implicitly; connection overhead dominates for fast local services.
- Files: `clod.py` (all requests.get/post calls: lines 304–310, 362–367, 403–410, 426–438, 489–498, 570, 627, 784, 837, 1497–1508, 1555–1575, 1717–1728).
- Cause: Lazy initialization; no persistent session management.
- Impact: Multiple requests per inference (tool calls, health checks) incur TCP handshake overhead; slightly slower round-trip times.
- Improvement path: Create module-level `_SESSION = requests.Session()` with connection pooling; reuse for all requests. Set pool size based on expected concurrency.

## Fragile Areas

**Session State as Mutable Dict with String Keys:**
- Files: `clod.py` (session_state dict created lines 2552–2565, mutated throughout handle_slash lines 2079–2515).
- Why fragile: No type hints; easy to typo key name (e.g., `session_state["mdoel"]` vs `session_state["model"]`); no validation on mutation; if slash command crashes mid-update, state is partially mutated; circular reference through "cfg" and "budget" makes testing harder.
- Safe modification: Define `SessionState` dataclass with typed fields; use `dataclasses.replace()` for immutable updates where possible; add invariant checks (e.g., "pipeline" and "model" are mutually exclusive).

**Docker Compose YAML Parsing Without Validation:**
- Files: `clod.py` (_get_service_volumes lines 1067–1100, docker-compose.yml).
- Why fragile: Parses docker-compose.yml with simple regex/string split; if compose file format changes or has comments in unexpected places, parsing breaks. Uses yaml.safe_load but fallback to manual parsing if yaml unavailable (line 1090).
- Safe modification: Always require PyYAML as dependency; document compose file structure; add validation schema check before parsing.

**Config File Path Assumptions:**
- Files: `clod.py` (lines 2665–2669 pin compose_file and dotenv_file to _clod_root).
- Why fragile: Stale config.json from previous run could reference old paths; reset at startup but user could manually edit config.json and point to non-existent files.
- Safe modification: Validate that compose_file and dotenv_file exist before using; if not, auto-reset to defaults. Add startup check: if both compose_file and dotenv_file are invalid, prompt user to re-run setup.

**Model Availability Checked Without Caching:**
- Files: `clod.py` (ollama_model_available lines 400–410 called from ensure_ollama_model lines 465–480, which is called on every infer() iteration if model not cached).
- Why fragile: If ollama_model_available() fails due to network, ensure_ollama_model() returns False, and infer() bails with error; no cache or memoization.
- Safe modification: Cache model availability in session_state with TTL; if check fails, assume model is available (optimistic) and let pull handle failure.

## Scaling Limits

**Memory Usage for Large Context Files:**
- Current: _gather_context() (lines 1680–1711) loads up to 2 candidate files per directory; truncates each file to MAX_CONTEXT_CHARS_PER_FILE (check value).
- Limit: If user indexes a large monorepo, memory can spike with many files; no streaming or pagination.
- Scaling path: Use generator-based file reading; stream files to LLM as newline-delimited JSON or line-by-line prompts instead of loading all into memory.

**Docker Compose Service Count:**
- Current: 8–10+ services (ollama, litellm, open-webui, nginx, searxng, chroma, pipelines, n8n, stable-diffusion, comfyui) across internal/gateway/default networks.
- Limit: Each service restart adds 5–10s latency; health check loop (lines 835–840) makes N requests in sequence (no parallelism).
- Scaling path: Use docker compose wait conditions; parallelize health checks with asyncio or concurrent.futures.

**Tool Call Loop Without Depth Limit:**
- Current: infer() (lines 2038–2073) loops up to 10 times for tool calls; no circuit breaker or cost accounting.
- Limit: If LLM tool calls in a loop (e.g., repeatedly calling bash_exec), could exhaust token budget or run forever.
- Scaling path: Add `max_tool_calls` config parameter; track token cost per tool call; break loop if cost exceeds threshold.

## Dependencies at Risk

**psutil Optional Dependency with Silent Failure:**
- Risk: psutil import at lines 34–39 fails silently (HAS_PSUTIL = False); query_system_info() and query_gpu_vram() return None if psutil unavailable, breaking GPU recommendations and startup banner.
- Files: `clod.py` (lines 34–39 import, lines 541–599 query_system_info, query_gpu_vram, recommend_model_for_vram).
- Impact: RTX GPU detection fails if nvidia-ml-py not installed; VRAM recommendations show "none"; model auto-selection has no fallback.
- Migration plan: Make psutil required; add nvidia-ml-py optional for CUDA GPU detection. If neither available, disable GPU-aware features gracefully with user warning.

**Requests Library Without Pin:**
- Risk: requirements.txt specifies `requests>=2.31.0` without upper bound; future major version (e.g., requests 4.0) could break API compatibility.
- Files: `requirements.txt` (line 1), `clod.py` (all requests.* calls).
- Impact: Installation on new system might pull incompatible version.
- Migration plan: Pin to `requests>=2.31.0,<4.0`; regularly update to latest minor version.

**LiteLLM Service Image (ghcr.io/berriai/litellm:main-latest):**
- Risk: docker-compose.yml (line 50) pulls `main-latest` tag, which is mutable and could introduce breaking changes.
- Files: `docker-compose.yml` (line 50).
- Impact: docker compose pull could silently upgrade and break API compatibility.
- Migration plan: Pin to specific LiteLLM version (e.g., `1.45.0`) and test before upgrading; use SemVer versioning.

## Missing Critical Features

**No Offline Mode for Pipelines:**
- Problem: /pipeline code_review requires claude-sonnet (LiteLLM); offline mode (lines 2005–2010, 2163–2170) strips pipeline and falls back to local model.
- Blocks: Two-stage pipeline workflows are unavailable offline; users must choose between pipeline and offline mode.
- Fix: Implement local two-stage pipelines using qwen2.5-coder locally instead of claude-sonnet; store local pipeline configs separately from cloud pipelines.

**No Conversation History Persistence Across Sessions:**
- Problem: Messages list (line 2567) is discarded on REPL exit; /save command (lines 2180–2185) saves to JSON but doesn't load previous sessions.
- Blocks: Long research workflows require manual history re-entry; no way to resume from saved session.
- Fix: Add /load command; auto-load latest saved session on startup (optional flag); store conversation metadata (timestamp, model, tokens used).

**No Model Quantization or Custom Model Loading:**
- Problem: All models must be in Ollama registry; no support for GPTQ, ONNX, or custom formats.
- Blocks: Users with custom fine-tuned models or quantized variants cannot use them.
- Fix: Add /load-model <url/path> command that downloads and registers new models with Ollama; document model format expectations.

## Test Coverage Gaps

**Interactive REPL Code Untestable (run_repl, handle_slash):**
- What's not tested:
  - All slash commands (lines 2092–2435): /model, /pipeline, /tools, /offline, /tokens, /system, /clear, /save, /index, /gpu, /mcp, /sd, /services, /help, /exit
  - Token budget prompts (lines 1856–1866)
  - REPL message loop (lines 2608–2638)
  - MCP server startup and context injection (lines 2575–2595)
- Files: `clod.py` (run_repl lines 2537–2638, handle_slash lines 2079–2515, check_token_thresholds lines 1846–1868, main lines 2659–2772).
- Risk: Regressions in user-facing REPL only caught at integration test time; slash command combinations (e.g., /offline on, /pipeline code_review) have no coverage.
- Priority: HIGH — these are the primary user interaction paths.
- Test approach: Mock PromptSession; inject test input strings; capture printed output; verify session_state mutations; parameterize over slash command variations.

**Stream Functions (stream_ollama, stream_openai_compat):**
- What's not tested:
  - Handling of empty streams (model returns no tokens)
  - Tool call streaming (event["type"] == "tool_call" case at line 1972)
  - Error events (event["type"] == "error" at line 1974)
  - Timeout during streaming
  - Connection drop mid-stream
- Files: `clod.py` (stream_ollama lines 1474–1508, stream_openai_compat lines 1531–1575, stream_and_render lines 1960–1985, infer lines 2038–2073 tool_calls handling).
- Risk: Tool use workflows untested; streaming error recovery not validated.
- Priority: MEDIUM.

**Index Mode (run_index_mode, _gather_context, project detection):**
- What's not tested:
  - File truncation logic (lines 1704–1705)
  - Multi-project indexing with concurrent LLM calls
  - Overwrite confirmation logic (lines 1770–1772, 1785–1789)
  - _detect_project_types with edge cases (symlinks, .git/config vs git/ directory)
- Files: `clod.py` (run_index_mode lines 1741–1811, _detect_project_types lines 1647–1658, _find_project_roots lines 1661–1677, _gather_context lines 1680–1711).
- Risk: Project detection may fail on unusual directory structures; index mode may silently skip projects.
- Priority: LOW (feature is optional).

**Service Health & Docker Integration:**
- What's not tested:
  - Service startup polling (lines 915–933)
  - Docker compose command failures (stderr capture)
  - /services reset logic with delete_mode variations (lines 1158–1182)
  - docker-compose YAML parsing edge cases (_get_service_volumes lines 1067–1100)
  - _offer_docker_startup user interaction (lines 948–997)
- Files: `clod.py` (_check_service_health lines 830–842, _offer_docker_startup lines 948–997, _reset_service lines 1118–1182, _get_service_volumes lines 1067–1100).
- Risk: Docker startup may fail silently; service reset could partially execute and leave state inconsistent.
- Priority: MEDIUM (affects deployment experience).

---

*Concerns audit: 2026-03-10*
