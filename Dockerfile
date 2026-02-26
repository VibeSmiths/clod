FROM python:3.12-slim

LABEL maintainer="$USER" \
      description="OmniAI — autonomous local AI vibecoder agent" \
      version="1.0"

# ── System deps ────────────────────────────────────────────────────────────────
# build-essential needed for chromadb C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps (own layer for cache efficiency) ───────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Source ─────────────────────────────────────────────────────────────────────
COPY omni-ai.py .
COPY omni-ctl.py .

# ── Persistent data dirs ───────────────────────────────────────────────────────
RUN mkdir -p /root/.omni_ai/sessions /app/backups

# ── Runtime config (override with -e at docker run) ───────────────────────────
# Ollama: on Linux use host-gateway; on Mac/Win use host.docker.internal
ENV OLLAMA_URL=http://host.docker.internal:11434
ENV SEARXNG_URL=http://searxng:8080
ENV CHROMA_URL=http://chroma:8000
ENV PIPELINES_URL=http://omni-pipelines:9099

VOLUME ["/root/.omni_ai", "/app/backups"]

# ── Entrypoint ─────────────────────────────────────────────────────────────────
# Interactive REPL by default; pass args for single-shot mode:
#   docker run -it omni-stack "build me a FastAPI server"
ENTRYPOINT ["python3", "omni-ai.py"]
