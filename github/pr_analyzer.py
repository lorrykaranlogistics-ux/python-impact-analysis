from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Set

from analysis.change_classifier import ChangeCategory, ChangeClassifier
from config import Settings


API_PATTERN = re.compile(r"[\'\"](/[-\w_/]+)[\'\"]")


@dataclass
class PRAnalysis:
    files_changed: int
    total_additions: int
    total_deletions: int
    sensitive_changes: List[str]
    endpoints: Set[str]
    categories: List[ChangeCategory]


class PRAnalyzer:
    def __init__(self, settings: Settings):
        self.classifier = ChangeClassifier(settings.sensitive_paths)

    def analyze(self, files: Iterable[Dict[str, int]]) -> PRAnalysis:
        additions = 0
        deletions = 0
        sensitive: Set[str] = set()
        categories: List[ChangeCategory] = []
        endpoints: Set[str] = set()
        count = 0
        for info in files:
            filename = info.get("filename", "")
            additions += info.get("additions", 0)
            deletions += info.get("deletions", 0)
            count += 1
            categories.append(self.classifier.classify(filename))
            if self.classifier.sensitive_changes([filename]):
                sensitive.add(filename)
            patch = info.get("patch") or ""
            for match in API_PATTERN.findall(patch):
                endpoints.add(match)
        return PRAnalysis(
            files_changed=count,
            total_additions=additions,
            total_deletions=deletions,
            sensitive_changes=sorted(sensitive),
            endpoints=endpoints,
            categories=categories,
        )

    def api_change_detected(self, categories: Iterable[ChangeCategory]) -> bool:
        return self.classifier.detects_api_change(categories)

    def database_change_detected(self, categories: Iterable[ChangeCategory]) -> bool:
        return self.classifier.detects_database_change(categories)
