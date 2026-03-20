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
    category_counts: Dict[str, int]
    payload_response_changes: bool
    changed_urls: Set[str]


class PRAnalyzer:
    def __init__(self, settings: Settings):
        self.classifier = ChangeClassifier(settings.sensitive_paths)

    def analyze(self, files: Iterable[Dict[str, int]]) -> PRAnalysis:
        additions = 0
        deletions = 0
        sensitive: Set[str] = set()
        categories: List[ChangeCategory] = []
        endpoints: Set[str] = set()
        category_counts: Dict[str, int] = {}
        count = 0
        payload_response_changes = False
        changed_urls: Set[str] = set()

        for info in files:
            filename = info.get("filename", "")
            additions += info.get("additions", 0)
            deletions += info.get("deletions", 0)
            count += 1
            category = self.classifier.classify(filename)
            categories.append(category)
            category_counts[category.value] = category_counts.get(category.value, 0) + 1
            if self.classifier.sensitive_changes([filename]):
                sensitive.add(filename)
            patch = info.get("patch") or ""
            for match in API_PATTERN.findall(patch):
                endpoints.add(match)

            # Heuristics for payload/response impact: request/response schema snippets, payload keys, and URL updates
            if re.search(r"\b(payload|request body|response body|schema|dto)\b", patch, flags=re.I):
                payload_response_changes = True
            for url_match in re.findall(r"[\'\"](/[-\w_/]+)[\'\"]", patch):
                changed_urls.add(url_match)

        return PRAnalysis(
            files_changed=count,
            total_additions=additions,
            total_deletions=deletions,
            sensitive_changes=sorted(sensitive),
            endpoints=endpoints,
            categories=categories,
            category_counts=category_counts,
            payload_response_changes=payload_response_changes,
            changed_urls=changed_urls,
        )

    def api_change_detected(self, categories: Iterable[ChangeCategory]) -> bool:
        return self.classifier.detects_api_change(categories)

    def database_change_detected(self, categories: Iterable[ChangeCategory]) -> bool:
        return self.classifier.detects_database_change(categories)
