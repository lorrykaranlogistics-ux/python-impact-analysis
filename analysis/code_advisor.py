from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


@dataclass
class CodeAdvice:
    endpoint: str
    file: str
    line: int
    current_code: str
    suggested_code: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "endpoint": self.endpoint,
            "file": self.file,
            "line": self.line,
            "current_code": self.current_code,
            "suggested_code": self.suggested_code,
            "reason": self.reason,
        }


def _format_class_name(service: str) -> str:
    safe = "".join(part.capitalize() for part in service.replace("-", "_").split("_") if part)
    return f"{safe or 'Service'}PayloadSchema"


def build_code_advice(
    local_matches: Dict[str, Iterable[Path]],
    changed_urls: Iterable[str],
    payload_response_changes: bool,
    impacted_services: Iterable[str],
) -> List[CodeAdvice]:
    primary_endpoint = next(iter(changed_urls), None)
    primary_service = next(iter(impacted_services), None) or "service"
    seen: Set[tuple[str, str]] = set()
    advice: List[CodeAdvice] = []

    for endpoint, files in local_matches.items():
        for path in files:
            key = (endpoint, str(path))
            if key in seen:
                continue
            seen.add(key)
            try:
                lines = path.read_text(errors="ignore").splitlines()
            except OSError:
                continue
            for idx, text in enumerate(lines, start=1):
                if endpoint not in text:
                    continue
                current = text.strip()
                suggestion = _build_suggestion(
                    endpoint=endpoint,
                    current=current,
                    primary_endpoint=primary_endpoint or endpoint,
                    payload_response_changes=payload_response_changes,
                    primary_service=primary_service,
                )
                reason = (
                    f"Downstream call to \"{endpoint}\" must align with the updated {primary_service} API."
                )
                advice.append(
                    CodeAdvice(
                        endpoint=endpoint,
                        file=str(path),
                        line=idx,
                        current_code=current,
                        suggested_code=suggestion,
                        reason=reason,
                    )
                )
                break
    return advice


def _build_suggestion(
    endpoint: str,
    current: str,
    primary_endpoint: str,
    payload_response_changes: bool,
    primary_service: str,
) -> str:
    suggestion_parts: List[str] = []
    if payload_response_changes:
        schema = _format_class_name(primary_service)
        suggestion_parts.append(
            f"{schema}.parse_obj(payload)",
        )
    route_snippet = current.replace(endpoint, primary_endpoint)
    suggestion_parts.append(route_snippet + "  # ensure payload matches new schema")
    return " | ".join(suggestion_parts)
