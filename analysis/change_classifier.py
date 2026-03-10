from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Iterable, List


class ChangeCategory(Enum):
    UI = "UI change"
    API = "API change"
    DATABASE = "database model change"
    CONFIG = "configuration change"
    TEST = "test change"


class ChangeClassifier:
    def __init__(self, sensitive_paths: Iterable[str]) -> None:
        self.sensitive_paths = list(sensitive_paths)

    def classify(self, file_path: str) -> ChangeCategory:
        lower = file_path.lower()
        if "test" in lower or "/tests/" in lower:
            return ChangeCategory.TEST
        if any(part in lower for part in ("route", "controller", "api", "graphql")):
            return ChangeCategory.API
        if "model" in lower or "schema" in lower or "dto" in lower:
            return ChangeCategory.DATABASE
        if "config" in lower or lower.endswith(('.env', '.yaml', '.yml')):
            return ChangeCategory.CONFIG
        return ChangeCategory.UI

    def sensitive_changes(self, files: Iterable[str]) -> List[str]:
        results: List[str] = []
        for path in files:
            if any(path.lower().startswith(prefix.lower()) for prefix in self.sensitive_paths):
                results.append(path)
        return results

    def detects_api_change(self, categories: Iterable[ChangeCategory]) -> bool:
        return any(cat == ChangeCategory.API for cat in categories)

    def detects_database_change(self, categories: Iterable[ChangeCategory]) -> bool:
        return any(cat == ChangeCategory.DATABASE for cat in categories)
