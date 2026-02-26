#!/usr/bin/env bash
# ai — OmniAI autonomous agent
#
# Usage:
#   ai                          interactive session
#   ai "do this thing"          single task, then exit
#
# The agent uses Ollama's native tool-calling API with qwen2.5-coder:14b.
# It executes shell commands, reads/writes files, searches the web, and more
# without any confirmation prompts.

exec ~/interpreter-venv/bin/python3 \
    ~/omni-stack/omni-ai.py "$@"
