"""
OmniAI — Claude Review Pipeline
================================
Registered automatically by the omni-pipelines container.

Flow:
  User message
    → Local Ollama (qwen2.5-coder:32b or configured model) generates a draft
    → Claude reviews the draft: fixes bugs, improves formatting, adds next-step plan
    → Streams the improved response back

Configure via Open-WebUI Pipelines Valves:
  ANTHROPIC_API_KEY  — required
  CLAUDE_MODEL       — default: claude-opus-4-6
  LOCAL_MODEL        — default: qwen2.5-coder:32b-instruct-q4_K_M
  OLLAMA_URL         — default: http://host-gateway:11434
  SKIP_LOCAL         — set to "true" to call Claude directly (no local draft)
"""

from typing import List, Union, Generator, Iterator, Optional
from pydantic import BaseModel
import requests
import json
import os


class Pipeline:

    class Valves(BaseModel):
        ANTHROPIC_API_KEY: str = ""
        CLAUDE_MODEL: str = "claude-opus-4-6"
        LOCAL_MODEL: str = "qwen2.5-coder:32b-instruct-q4_K_M"
        OLLAMA_URL: str = "http://host-gateway:11434"
        SKIP_LOCAL: str = "false"
        REVIEW_SYSTEM: str = (
            "You are a senior engineer reviewing a draft response from a local AI model.\n"
            "Your tasks:\n"
            "1. Fix any bugs, incorrect logic, or broken code\n"
            "2. Improve formatting and clarity — use markdown code blocks\n"
            "3. If the response involves multiple steps or a plan, add a concise "
            "'## Next Steps' section at the end\n"
            "4. Keep the same language and tone — just make it correct and clean\n"
            "Be concise. Do not add unnecessary padding."
        )

    def __init__(self):
        self.name = "OmniAI Claude Review"
        self.type = "pipe"
        self.id = "claude_review"
        self.valves = self.Valves(
            ANTHROPIC_API_KEY=os.getenv("ANTHROPIC_API_KEY", ""),
            OLLAMA_URL=os.getenv("OLLAMA_URL", "http://host-gateway:11434"),
        )

    async def on_startup(self):
        has_key = bool(self.valves.ANTHROPIC_API_KEY)
        print(f"[claude_review] ready — API key: {'set' if has_key else 'MISSING'}")

    async def on_shutdown(self):
        pass

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[dict],
        body: dict,
    ) -> Union[str, Generator, Iterator]:

        if not self.valves.ANTHROPIC_API_KEY:
            yield (
                "⚠️ **No Anthropic API key configured.**\n\n"
                "Go to **Pipelines → Valves** and set `ANTHROPIC_API_KEY`.\n"
                "Or add it to your `.env` file and restart the stack."
            )
            return

        skip_local = self.valves.SKIP_LOCAL.lower() == "true"
        local_draft = ""

        # ── Step 1: local Ollama draft ─────────────────────────────────────────
        if not skip_local:
            yield "⟳ *Drafting locally…*\n\n"
            try:
                resp = requests.post(
                    f"{self.valves.OLLAMA_URL}/api/chat",
                    json={
                        "model": self.valves.LOCAL_MODEL,
                        "messages": messages,
                        "stream": False,
                        "options": {"num_ctx": 16384},
                    },
                    timeout=180,
                )
                resp.raise_for_status()
                local_draft = resp.json().get("message", {}).get("content", "")
            except Exception as e:
                yield f"✗ Local model error: {e}\n\nFalling back to Claude only.\n\n"
                skip_local = True

        if local_draft:
            yield "---\n*Local draft ready — Claude reviewing…*\n\n---\n\n"

        # ── Step 2: Claude review / direct call ───────────────────────────────
        if local_draft:
            claude_user_content = (
                f"**User's request:**\n{user_message}\n\n"
                f"**Local AI draft:**\n{local_draft}\n\n"
                "Review and improve the draft per your instructions."
            )
        else:
            # Straight Claude call — no local draft
            claude_user_content = user_message

        claude_messages = [{"role": "user", "content": claude_user_content}]
        # Preserve prior conversation context for Claude
        if len(messages) > 1:
            history = messages[:-1]  # everything except the current user message
            claude_messages = [
                m for m in history if m["role"] in ("user", "assistant")
            ] + claude_messages

        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.valves.ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.valves.CLAUDE_MODEL,
                    "max_tokens": 8192,
                    "system": self.valves.REVIEW_SYSTEM,
                    "messages": claude_messages,
                    "stream": True,
                },
                stream=True,
                timeout=120,
            )
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8")
                if not decoded.startswith("data: "):
                    continue
                data = decoded[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    if chunk.get("type") == "content_block_delta":
                        delta = chunk.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")
                except json.JSONDecodeError:
                    continue

        except requests.HTTPError as e:
            yield f"\n\n✗ Anthropic API error {e.response.status_code}: {e.response.text}\n"
        except Exception as e:
            yield f"\n\n✗ Claude call failed: {e}\n"
