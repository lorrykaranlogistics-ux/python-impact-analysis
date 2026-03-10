from __future__ import annotations

from typing import Dict

import httpx

from .base_llm import BaseLLM


class GeminiProvider(BaseLLM):
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = api_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def summarize(self, prompt: str, context: Dict[str, str]) -> str:
        payload = {
            "prompt": {
                "text": prompt,
            },
            "maxOutputTokens": 512,
            "temperature": 0.2,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = await self.client.post(self.api_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if candidates:
            return candidates[0].get("output", "").strip()
        return data.get("output", "").strip()

    async def close(self) -> None:
        await self.client.aclose()
