#!/usr/bin/env bash
# Install voice pipeline dependencies

set -euo pipefail

source "$HOME/ai-audio-venv/bin/activate"

pip install sounddevice scipy pynput xdotool pyperclip
pip install faster-whisper  # already installed, no-op

# xdotool for typing into active window
sudo pacman -S --noconfirm xdotool

echo ""
echo "=== Voice pipeline ready ==="
echo "Run: source ~/ai-audio-venv/bin/activate.fish"
echo "     python ~/omni-stack/voice-to-aider.py"
echo ""
echo "Then open Aider in another terminal:"
echo "     source ~/aider-venv/bin/activate.fish"
echo "     cd your-project"
echo "     aider --model ollama/qwen2.5-coder:14b"
echo ""
echo "Hold Super+\` to speak, release to send."
