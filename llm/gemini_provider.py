from __future__ import annotations

from typing import Any, Dict, List

import httpx

from .base_llm import BaseLLM


class GeminiProvider(BaseLLM):
    def __init__(self, api_key: str, api_url: str):
        self.api_key = api_key
        self.api_url = self._normalize_api_url(api_url)
        self.client = httpx.AsyncClient(timeout=30.0)

    def _normalize_api_url(self, api_url: str) -> str:
        base, sep, query = api_url.partition("?")
        if ":generateContent" not in base:
            if base.endswith(":generate"):
                base = f"{base[: -len(':generate')]}:generateContent"
            else:
                base = base.rstrip("/") + ":generateContent"
        api_url = base + (f"?{query}" if query else "")

        if "key=" not in api_url:
            separator = "&" if "?" in api_url else "?"
            api_url = f"{api_url}{separator}key={self.api_key}"

        return api_url

    async def summarize(self, prompt: str, context: Dict[str, str]) -> str:
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 512,
            },
        }
        try:
            response = await self.client.post(self.api_url, json=payload)
            response.raise_for_status()
            return self._extract_candidate_text(response.json())
        except httpx.HTTPStatusError as exc:
            text = exc.response.text if exc.response is not None else str(exc)
            status = exc.response.status_code if exc.response is not None else "unknown"
            return f"LLM unavailable (Gemini HTTP {status}): {text}"
        except Exception as exc:
            return f"LLM unavailable (Gemini error): {exc}"

    def _extract_candidate_text(self, data: Dict[str, Any]) -> str:
        candidates: List[Dict[str, Any]] = data.get("candidates", [])
        if candidates:
            text = self._extract_text_from_candidate(candidates[0])
            if text:
                return text
        return data.get("output", "").strip() or ""

    @staticmethod
    def _extract_text_from_candidate(candidate: Dict[str, Any]) -> str | None:
        content = candidate.get("content") or {}
        parts = content.get("parts", [])
        for part in parts:
            text = part.get("text")
            if text:
                return text.strip()
        text = candidate.get("output") or candidate.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
        return None

    async def close(self) -> None:
        await self.client.aclose()
