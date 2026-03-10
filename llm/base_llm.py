from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class BaseLLM(ABC):
    @abstractmethod
    async def summarize(self, prompt: str, context: Dict[str, str]) -> str:
        """Generate a summary from provided prompt and context."""

    async def close(self) -> None:
        return None
