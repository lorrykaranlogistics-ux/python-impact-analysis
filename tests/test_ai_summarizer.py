from llm.ai_summarizer import AISummarizer
from config import Settings
import pytest


def test_llm_provider_environment_priority_gemini():
    settings = Settings(
        gemini_api_key="x",
        gemini_api_url="https://example.com/v1",
        claude_api_key="x",
        claude_api_url="https://example.com/v1",
        llm_provider="gemini",
    )

    summarizer = AISummarizer(settings)
    assert len(summarizer.providers) == 1
    assert summarizer.providers[0].__class__.__name__ == "GeminiProvider"


def test_llm_provider_environment_auto_chooses_available():
    settings = Settings(
        gemini_api_key="x",
        gemini_api_url="https://example.com/v1",
        llm_provider="auto",
    )

    summarizer = AISummarizer(settings)
    # only gemini available in this config
    assert len(summarizer.providers) == 1
    assert summarizer.providers[0].__class__.__name__ == "GeminiProvider"


def test_llm_provider_falls_back_to_auto_when_configured():
    settings = Settings(
        gemini_api_key="x",
        gemini_api_url="https://example.com/v1",
        claude_api_key="x",
        claude_api_url="https://example.com/v1",
        llm_provider="auto",
    )

    summarizer = AISummarizer(settings)
    assert any(p.__class__.__name__ == "GeminiProvider" for p in summarizer.providers)


def test_gemini_provider_url_normalizes_generate_and_key():
    from llm.gemini_provider import GeminiProvider

    provider = GeminiProvider(
        api_key="testkey",
        api_url="https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro",
    )

    assert ":generate" in provider.api_url
    assert "key=testkey" in provider.api_url
