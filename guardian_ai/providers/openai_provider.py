from __future__ import annotations
import os
import httpx
from typing import Dict, Optional, Any
from guardian_ai.providers.base import LLMProvider, LLMResponse

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model

    def get_provider_name(self) -> str:
        return f"OpenAI ({self.model})"

    def generate(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.2) -> LLMResponse:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 4096
        }

        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        text = ""
        choices = data.get("choices", [])
        if choices and "message" in choices[0]:
            text = choices[0]["message"].get("content", "")

        tokens = data.get("usage", {}).get("total_tokens", 0)

        return LLMResponse(
            content=text,
            model=self.model,
            tokens_used=tokens,
            raw=data
        )
