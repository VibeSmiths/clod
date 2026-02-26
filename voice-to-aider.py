#!/usr/bin/env python3
"""
Voice → Whisper → Aider pipeline.
Hold Super+Space to record, release to transcribe and send to Aider.

Requirements:
  pip install faster-whisper sounddevice numpy pynput pyperclip
  aider must be running in a terminal (it reads from stdin via subprocess or xdotool)
"""

import io
import os
import sys
import queue
import threading
import tempfile
import subprocess
import numpy as np
import sounddevice as sd
from pynput import keyboard
from faster_whisper import WhisperModel

# ── Config ────────────────────────────────────────────────────────────────────
WHISPER_MODEL   = "large-v3-turbo"
WHISPER_DEVICE  = "cuda"
SAMPLE_RATE     = 16000
HOTKEY          = {keyboard.Key.cmd, keyboard.KeyCode.from_char('`')}  # Super+`
AIDER_MODEL     = "ollama/qwen2.5-coder:14b"

# ── State ─────────────────────────────────────────────────────────────────────
recording       = False
audio_chunks    = []
current_keys    = set()

print("Loading Whisper large-v3-turbo on CUDA...")
model = WhisperModel(WHISPER_MODEL, device=WHISPER_DEVICE, compute_type="float16")
print("Ready. Hold Super+` to speak, release to transcribe.")
print()

def record_audio():
    global audio_chunks
    audio_chunks = []
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32") as stream:
        while recording:
            chunk, _ = stream.read(SAMPLE_RATE // 10)  # 100ms chunks
            audio_chunks.append(chunk)

def transcribe_and_send():
    if not audio_chunks:
        return
    audio = np.concatenate(audio_chunks, axis=0).flatten()
    if len(audio) < SAMPLE_RATE * 0.3:  # ignore < 0.3s
        return

    print("Transcribing...", end=" ", flush=True)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        import scipy.io.wavfile as wav
        wav.write(f.name, SAMPLE_RATE, audio)
        segments, _ = model.transcribe(f.name, language="en")
        text = " ".join(s.text.strip() for s in segments).strip()
        os.unlink(f.name)

    if not text:
        print("(silence)")
        return

    print(f'"{text}"')

    # Type into the active window via xdotool
    subprocess.run(["xdotool", "type", "--clearmodifiers", "--", text], check=False)
    # Send Enter to submit to aider
    subprocess.run(["xdotool", "key", "Return"], check=False)

record_thread = None

def on_press(key):
    global recording, record_thread
    current_keys.add(key)
    if HOTKEY.issubset(current_keys) and not recording:
        recording = True
        print("\n[Recording...]", end=" ", flush=True)
        record_thread = threading.Thread(target=record_audio, daemon=True)
        record_thread.start()

def on_release(key):
    global recording
    try:
        current_keys.discard(key)
    except Exception:
        pass
    if key in HOTKEY and recording:
        recording = False
        if record_thread:
            record_thread.join(timeout=2)
        threading.Thread(target=transcribe_and_send, daemon=True).start()

with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
