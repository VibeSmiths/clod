#!/usr/bin/env bash
# OmniAI launcher — opens the full TUI home base in a dedicated Konsole window
exec konsole \
  --title "OmniAI" \
  --hide-menubar \
  --hide-tabbar \
  --nofork \
  -e ~/interpreter-venv/bin/python3 \
     ~/omni-stack/omni-panel.py
