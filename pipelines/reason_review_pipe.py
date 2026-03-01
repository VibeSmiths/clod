"""
AI — Reasoning Review Pipeline
Stage 1: deepseek-r1:14b (local Ollama) — deep analysis, chain-of-thought
Stage 2: claude-sonnet (via LiteLLM)    — senior architect structures and refines output
"""

import json
import os
import re
from typing import Generator, Iterator, List, Union

import requests
from pydantic import BaseModel


class Pipeline:

    class Valves(BaseModel):
        LOCAL_MODEL: str = "deepseek-r1:14b"
        CLAUDE_MODEL: str = "claude-sonnet"
        OLLAMA_URL: str = "http://ollama:11434"
        LITELLM_URL: str = "http://litellm:4000"
        LITELLM_API_KEY: str = "sk-local-dev"
        SKIP_LOCAL: str = "false"
        REVIEW_SYSTEM: str = (
            "You are a senior architect and analyst reviewing reasoning from a local AI model.\n"
            "The model has performed chain-of-thought analysis (think tags already stripped).\n"
            "Your tasks:\n"
            "1. Extract the core conclusions and discard verbose reasoning noise\n"
            "2. Verify logical consistency — flag any flawed or unsupported steps\n"
            "3. Structure the output clearly: problem statement, analysis, recommendation\n"
            "4. Add quantitative estimates or risk assessments where they are absent\n"
            "5. End with a concise '## Decision / Recommendation' section\n"
            "Be precise. Use headers and bullet points. No padding."
        )

    def __init__(self):
        self.name = "AI Reasoning Review"
        self.type = "pipe"
        self.id = "reason_review"
        self.valves = self.Valves(
            OLLAMA_URL=os.getenv("OLLAMA_URL", "http://ollama:11434"),
            LITELLM_URL=os.getenv("LITELLM_BASE_URL", "http://litellm:4000"),
            LITELLM_API_KEY=os.getenv("LITELLM_API_KEY", "sk-local-dev"),
        )

    async def on_startup(self):
        print(
            f"[reason_review] ready — "
            f"local={self.valves.LOCAL_MODEL} "
            f"claude={self.valves.CLAUDE_MODEL}"
        )

    async def on_shutdown(self):
        pass

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: List[dict],
        body: dict,
    ) -> Union[str, Generator, Iterator]:

        skip_local = self.valves.SKIP_LOCAL.lower() == "true"
        local_draft = ""

        if not skip_local:
            yield "*Reasoning locally (deepseek-r1:14b)…*\n\n"
            try:
                resp = requests.post(
                    f"{self.valves.OLLAMA_URL}/api/chat",
                    json={
                        "model": self.valves.LOCAL_MODEL,
                        "messages": messages,
                        "stream": False,
                        "options": {"num_ctx": 16384},
                    },
                    timeout=300,
                )
                resp.raise_for_status()
                local_draft = resp.json().get("message", {}).get("content", "")

                # Strip DeepSeek chain-of-thought blocks
                if local_draft:
                    local_draft = re.sub(
                        r"<think>.*?</think>", "", local_draft, flags=re.DOTALL
                    ).strip()

            except Exception as e:
                yield f"> Local model error: {e}\n> Falling back to Claude only.\n\n"
                skip_local = True

        if local_draft:
            yield "\n---\n*Claude reviewing…*\n\n---\n\n"

        if local_draft:
            claude_user_content = (
                f"**User's request:**\n{user_message}\n\n"
                f"**Local AI draft:**\n{local_draft}\n\n"
                "Review and improve the draft per your instructions."
            )
        else:
            claude_user_content = user_message

        history = [m for m in messages[:-1] if m["role"] in ("user", "assistant")]
        claude_messages = history + [{"role": "user", "content": claude_user_content}]

        try:
            resp = requests.post(
                f"{self.valves.LITELLM_URL}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.valves.LITELLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.valves.CLAUDE_MODEL,
                    "messages": [
                        {"role": "system", "content": self.valves.REVIEW_SYSTEM},
                    ] + claude_messages,
                    "max_tokens": 8192,
                    "stream": True,
                },
                stream=True,
                timeout=180,
            )
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8") if isinstance(line, bytes) else line
                if not decoded.startswith("data: "):
                    continue
                data = decoded[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    text = (
                        chunk.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if text:
                        yield text
                except json.JSONDecodeError:
                    continue

        except requests.HTTPError as e:
            body_text = e.response.text if e.response else "no body"
            yield f"\n\n> LiteLLM error {e.response.status_code}: {body_text}\n"
        except Exception as e:
            yield f"\n\n> Claude call failed: {e}\n"
