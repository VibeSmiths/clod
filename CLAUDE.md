## Key Systems

### LLM / Models
- Default: `qwen2.5-coder:14b` (Ollama at localhost:11434)
- Reason: `deepseek-r1:14b`
- Vision: `qwen2.5vl:7b`
- Chat: `llama3.1:8b` (more conversational)
- Big: `qwen2.5-coder:32b-instruct-q4_K_M` (RTX 5070 Ti has 24GB, can run this)
- Switch with `/model <name>` in REPL

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
