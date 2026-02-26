#!/usr/bin/env bash
# Sets up Aider (AI coding agent) pointed at local Ollama

set -euo pipefail

VENV="$HOME/aider-venv"

echo "=== Creating Aider venv ==="
python3 -m venv "$VENV"
source "$VENV/bin/activate"
pip install --upgrade pip
pip install aider-chat

echo ""
echo "=== Aider installed ==="
echo ""
echo "Usage:"
echo "  source $VENV/bin/activate"
echo "  cd your-project"
echo "  aider --model ollama/qwen2.5-coder:14b"
echo "  aider --model ollama/qwen2.5-coder:32b-instruct-q4_K_M  # for harder tasks"
