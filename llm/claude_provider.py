from __future__ import annotations

from typing import Dict

import httpx

from .base_llm import BaseLLM


class ClaudeProvider(BaseLLM):
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def summarize(self, prompt: str, context: Dict[str, str]) -> str:
        payload = {
            "model": "claude-3.5",
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "max_tokens_to_sample": 512,
        }
        response = await self.client.post(
            self.api_url,
            json=payload,
            headers={"x-api-key": self.api_key},
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("completion") or data.get("results", [{}])[0].get("content", "")
        return text.strip()

    async def close(self) -> None:
        await self.client.aclose()
