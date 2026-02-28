"""
OmniAI — Code Review Pipeline
Stage 1: qwen2.5-coder:32b (local Ollama) — generates code solution
Stage 2: claude-sonnet (via LiteLLM)      — senior engineer review
"""

import json
import os
import re
from typing import Generator, Iterator, List, Union

import requests
from pydantic import BaseModel


class Pipeline:

    class Valves(BaseModel):
        LOCAL_MODEL: str = "qwen2.5-coder:32b-instruct-q4_K_M"
        CLAUDE_MODEL: str = "claude-sonnet"
        OLLAMA_URL: str = "http://ollama:11434"
        LITELLM_URL: str = "http://litellm:4000"
        LITELLM_API_KEY: str = "sk-local-dev"
        SKIP_LOCAL: str = "false"
        REVIEW_SYSTEM: str = (
            "You are a senior software engineer conducting a code review.\n"
            "You have received a draft solution from a local AI model.\n"
            "Your tasks:\n"
            "1. Fix any bugs, logic errors, or security vulnerabilities\n"
            "2. Improve code quality: naming, structure, error handling, edge cases\n"
            "3. Ensure idiomatic use of the language and relevant best practices\n"
            "4. Add or correct docstrings and inline comments where the logic is non-obvious\n"
            "5. If the solution spans multiple components, add a '## Architecture Notes' section\n"
            "6. End with a concise '## Next Steps' if further work is implied\n"
            "Use markdown code blocks with language tags. Be direct — no filler."
        )

    def __init__(self):
        self.name = "OmniAI Code Review"
        self.type = "pipe"
        self.id = "code_review"
        self.valves = self.Valves(
            OLLAMA_URL=os.getenv("OLLAMA_URL", "http://ollama:11434"),
            LITELLM_URL=os.getenv("LITELLM_BASE_URL", "http://litellm:4000"),
            LITELLM_API_KEY=os.getenv("LITELLM_API_KEY", "sk-local-dev"),
        )

    async def on_startup(self):
        print(
            f"[code_review] ready — "
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
            yield "*Drafting code locally (qwen2.5-coder:32b)…*\n\n"
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
