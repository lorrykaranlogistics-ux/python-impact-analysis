from __future__ import annotations

from typing import Dict, List

from .base_llm import BaseLLM
from .claude_provider import ClaudeProvider
from .gemini_provider import GeminiProvider
from utils.logger import setup_logger
from config import Settings


logger = setup_logger("impact.ai.llm")


class AISummarizer:
    def __init__(self, settings: Settings):
        self.providers: List[BaseLLM] = []

        provider_pref = (settings.llm_provider or "auto").strip().lower()

        if provider_pref in ("gemini", "auto") and settings.gemini_api_key and settings.gemini_api_url:
            self.providers.append(GeminiProvider(settings.gemini_api_key, str(settings.gemini_api_url)))

        if provider_pref in ("claude", "auto") and settings.claude_api_key and settings.claude_api_url:
            self.providers.append(ClaudeProvider(settings.claude_api_key, str(settings.claude_api_url)))

        if provider_pref == "gemini" and not any(isinstance(p, GeminiProvider) for p in self.providers):
            raise RuntimeError("Gemini provider requested but not configured")

        if provider_pref == "claude" and not any(isinstance(p, ClaudeProvider) for p in self.providers):
            raise RuntimeError("Claude provider requested but not configured")

        if not self.providers:
            raise RuntimeError("No LLM providers configured")

    async def summarize(self, context: Dict[str, str]) -> str:
        prompt = self._build_prompt(context)
        logger.info(
            "Generating AI summary (%s) for repo=%s target=%s",
            context.get("analysis_mode"),
            context.get("repository"),
            context.get("target_ref"),
        )

        for provider in self.providers:
            provider_name = provider.__class__.__name__
            logger.info("Invoking %s provider", provider_name)
            try:
                result = await provider.summarize(prompt, context)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception(
                    "Exception from %s while generating summary", provider_name
                )
                continue

            snippet = (result or "").replace("\n", " ")
            if len(snippet) > 200:
                snippet = f"{snippet[:197]}..."

            if result:
                logger.info(
                    "%s returned summary (%s chars): %s",
                    provider_name,
                    len(result),
                    snippet,
                )
            else:
                logger.warning("%s returned empty summary", provider_name)
            return result

        logger.error(
            "All LLM providers failed for repo=%s target=%s",
            context.get("repository"),
            context.get("target_ref"),
        )
        return "LLM summary unavailable (providers failed)."

    def _build_prompt(self, context: Dict[str, str]) -> str:
        lines = ["Summarize the PR impact:"]
        for key, value in context.items():
            lines.append(f"{key}: {value}")
        lines.append("Provide: summary, impact explanation, risky areas.")
        lines.append("Explicitly identify the current change details (files changed, additions/deletions, sensitive paths, endpoints).")
        lines.append("Predict how this change will impact downstream systems (local and remote).")
        lines.append("Explicitly identify which external repositories or services are affected.")
        lines.append("Provide code-level remediation guidance (pseudocode or skeleton) for downstream services that need fix/backfill based on new payload/response/URL contract changes.")
        lines.append("Provide a concise remediation/suggestion section: what to do next, how to mitigate risk, and what to verify before merge.")
        lines.append("If uncertain, explain assumptions and recommend data points to confirm.")
        return "\n".join(lines)

    async def close(self) -> None:
        for provider in self.providers:
            await provider.close()
