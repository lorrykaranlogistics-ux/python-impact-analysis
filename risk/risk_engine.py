from __future__ import annotations

from typing import Dict, Iterable, Optional


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
        category_counts: Optional[Dict[str, int]] = None,
        payload_response_changes: bool = False,
        changed_urls: Optional[Iterable[str]] = None,
    ) -> dict:
        self.score = 0
        self.score += files_changed

        # More granular category-aware scoring
        if category_counts is None:
            category_counts = {}

        api_count = category_counts.get("API change", 0)
        db_count = category_counts.get("database model change", 0)
        config_count = category_counts.get("configuration change", 0)
        test_count = category_counts.get("test change", 0)
        ui_count = category_counts.get("UI change", 0)

        self.score += api_count * 20
        self.score += db_count * 30
        self.score += config_count * 15
        # Test touch points can reduce risk if they accompany other changes
        self.score -= min(test_count * 5, 20)
        self.score += ui_count * 5

        # Sensitive paths are still high priority
        sensitive_count = len(list(sensitive_changes))
        self.score += sensitive_count * 10

        # Existing impacts
        impacted_count = len(list(impacted_repos))
        self.score += impacted_count * 20
        self.score += len(list(regression_failures)) * 50

        if payload_response_changes:
            self.score += 20
        changed_url_count = len(list(changed_urls)) if changed_urls is not None else 0
        self.score += min(changed_url_count * 10, 30)

        self.score = max(0, min(self.score, 100))

        risk_level = self._get_risk_level(self.score)
        return {"score": self.score, "level": risk_level}

    def _get_risk_level(self, score: int) -> str:
        if score <= 30:
            return "LOW"
        if score <= 80:
            return "MEDIUM"
        if score <= 140:
            return "HIGH"
        return "CRITICAL"
