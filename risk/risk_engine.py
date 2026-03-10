from __future__ import annotations

from typing import Iterable


class RiskEngine:
    def __init__(self) -> None:
        self.score = 0

    def evaluate(
        self,
        files_changed: int,
        sensitive_changes: Iterable[str],
        api_change: bool,
        db_model_change: bool,
        impacted_repos: Iterable[str],
        regression_failures: Iterable[str],
    ) -> dict:
        self.score = 0
        self.score += files_changed
        if sensitive_changes:
            self.score += 10
        if db_model_change:
            self.score += 40
        if api_change:
            self.score += 30
        impacted_count = len(list(impacted_repos))
        self.score += impacted_count * 20
        self.score += len(list(regression_failures)) * 50
        risk_level = self._get_risk_level(self.score)
        return {"score": self.score, "level": risk_level}

    def _get_risk_level(self, score: int) -> str:
        if score <= 25:
            return "LOW"
        if score <= 60:
            return "MEDIUM"
        if score <= 100:
            return "HIGH"
        return "CRITICAL"
