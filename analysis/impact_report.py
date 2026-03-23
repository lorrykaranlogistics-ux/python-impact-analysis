from __future__ import annotations

from typing import Any, Dict, List, Set

CORE_MONITORED_SERVICES: List[str] = [
    "users",
    "notifications",
    "orders",
    "products",
    "payments",
]

DOWNSTREAM_MAPPING: Dict[str, List[str]] = {
    "users": ["orders", "payments", "products"],
    "orders": ["payments", "products"],
    "payments": [],
    "products": [],
    "notifications": [],
}


def sanitize_ref(ref: str) -> str:
    return ref.replace("/", "_").replace(" ", "_")


def detect_core_service_impact(services: List[str]) -> List[str]:
    impacted_core: Set[str] = set()
    for service in services:
        normalized = service.lower()
        for core in CORE_MONITORED_SERVICES:
            if core in normalized:
                impacted_core.add(core)
    return sorted(impacted_core)


def build_solution_suggestion(
    risk: Dict[str, Any],
    impacted_services: List[str],
    downstream_services: List[str],
    sensitive_changes: List[str],
    api_change: bool,
    db_model_change: bool,
    impacted_core_services: List[str] | None = None,
    payload_response_changes: bool = False,
    changed_urls: List[str] | None = None,
) -> str:
    suggestions: List[str] = []
    suggestions.append(f"Risk score {risk['score']} ({risk['level']})")

    if impacted_services:
        suggestions.append(
            f"Impacted services/repositories detected: {', '.join(impacted_services)}"
        )
    else:
        suggestions.append("No impacted services/repositories detected by static scan.")

    if sensitive_changes:
        suggestions.append("Sensitive paths/files changed; require extra review and security signoff.")
    if api_change:
        suggestions.append("API behavior changed; run API contract tests and notify downstream consumers.")
    if db_model_change:
        suggestions.append("Database model change detected; coordinate migration scripts and freeze dependency upgrades.")
    if downstream_services:
        suggestions.append(
            f"Predicted downstream impacted services: {', '.join(downstream_services)}. "
            "Validate each service contract, adjust payload/response mappings, and run downstream tests."
        )
    if impacted_services and (
        "orders" in impacted_services
        or "payments" in impacted_services
        or "products" in impacted_services
    ):
        suggestions.append(
            "Downstream core services flagged: run full e2e flow and regression for orders/payments/products."
        )
    if payload_response_changes:
        suggestions.append(
            "Payload/response schema changes detected; verify dependent consumers still pass contract tests."
        )
    if changed_urls:
        suggestions.append("URL route modifications detected; update API gateway/consumer docs and integrations.")
    if impacted_core_services:
        suggestions.append(
            f"Monitored core services affected: {', '.join(impacted_core_services)}."
        )

    if risk["level"] in ("HIGH", "CRITICAL"):
        suggestions.append(
            "Immediate action: block merge until regression pipelines pass, add/adjust tests, and issue cross-service rollout plan."
        )
    elif risk["level"] == "MEDIUM":
        suggestions.append(
            "Action: prioritize end-to-end tests, manual validation of affected endpoints, and team communication."
        )
    else:
        suggestions.append(
            "Action: continue with standard review and deploy checks; monitor impacted paths post-release."
        )

    return " ".join(suggestions)


def build_code_suggestions(
    changed_urls: List[str],
    payload_response_changes: bool,
    impacted_services: List[str],
    sensitive_changes: List[str],
    endpoints: List[str],
) -> List[str]:
    suggestions: List[str] = []
    primary_service = impacted_services[0] if impacted_services else "this service"

    if payload_response_changes:
        suggestions.append(
            f"Add a typed schema or dataclass for {primary_service}'s payload/response and validate it in the handler, e.g.:\n"
            "```\nclass PayloadSchema(BaseModel):\n    # mirror the new fields\n```\n"
            "Use the schema during request parsing and response shaping."
        )

    if changed_urls:
        suggestions.append(
            "Update downstream client calls to the new routes, for example replace "
            f"`httpx.post('{changed_urls[0]}', ...)` or JS `fetch('{changed_urls[0]}')` with the updated parameters."
        )

    if sensitive_changes:
        suggestions.append(
            "Because sensitive paths changed, wrap the updated logic in dedicated guards (middleware/auth helpers) or add feature flags for gradual rollout."
        )
    elif endpoints:
        sdk_targets = ", ".join(sorted(set(endpoints)))
        suggestions.append(f"Regenerate or patch client SDKs that hit {sdk_targets} so they send the new payload shape.")

    if not suggestions:
        suggestions.append("No automatic code fix suggested; review the diff to determine the appropriate edits.")

    return suggestions
