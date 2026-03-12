from __future__ import annotations

from typing import Dict, Iterable, List

from .base_llm import BaseLLM
from .claude_provider import ClaudeProvider
from .gemini_provider import GeminiProvider
from config import Settings


class AISummarizer:
    def __init__(self, settings: Settings):
        self.providers: List[BaseLLM] = []
        if settings.claude_api_key and settings.claude_api_url:
            self.providers.append(ClaudeProvider(settings.claude_api_key, str(settings.claude_api_url)))
        if settings.gemini_api_key and settings.gemini_api_url:
            self.providers.append(GeminiProvider(settings.gemini_api_key, str(settings.gemini_api_url)))
        if not self.providers:
            raise RuntimeError("No LLM providers configured")

    async def summarize(self, context: Dict[str, str]) -> str:
        prompt = self._build_prompt(context)
        for provider in self.providers:
            try:
                return await provider.summarize(prompt, context)
            except Exception:
                continue
        return "LLM summary unavailable (providers failed)."

    def _build_prompt(self, context: Dict[str, str]) -> str:
        lines = ["Summarize the PR impact:"]
        for key, value in context.items():
            lines.append(f"{key}: {value}")
        lines.append("Provide: summary, impact explanation, risky areas.")
        return "\n".join(lines)

    async def close(self) -> None:
        for provider in self.providers:
            await provider.close()
