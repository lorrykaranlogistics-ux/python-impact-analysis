from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Set
from urllib.parse import urlparse

import httpx

from config import Settings
from github.github_client import GitHubClient
from github.pr_analyzer import PRAnalyzer
from gitlab.gitlab_client import GitLabClient
from gitlab.regression_runner import RegressionRunner
from analysis.dependency_scanner import DependencyScanner
from risk.risk_engine import RiskEngine
from llm.ai_summarizer import AISummarizer
from utils.logger import setup_logger
from pathlib import Path
import subprocess

logger = setup_logger()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("impact-analysis-agent")
    parser.add_argument("--repo", required=True, help="GitHub repo in owner/name form")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pr", type=int, help="PR number to analyze")
    group.add_argument(
        "--branch",
        help="GitHub branch to compare against --base-ref (default 'main')",
    )
    group.add_argument(
        "--tag",
        help="GitHub tag to compare against --base-ref (default 'main')",
    )
    parser.add_argument(
        "--scan-local-repos",
        nargs="+",
        type=Path,
        help="Optional local directories containing other services to scan (e.g. users notifications products)",
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run test suite in impacted local microservices (npm test) before regression triggers",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="Base ref used when analyzing a branch or tag (default: main)",
    )
    return parser.parse_args()


def normalize_repo(repo: str) -> str:
    candidate = repo.strip()

    # Strip .git suffix
    if candidate.endswith(".git"):
        candidate = candidate[:-4]

    # Handle raw URLs and embedded duplicated URL fragments
    if candidate.startswith("http://") or candidate.startswith("https://"):
        parsed = urlparse(candidate)
        candidate = parsed.path.lstrip("/")

    # In case of concatenated URL strings (e.g. .../repohttps://gitlab.com/owner/repo), cut at the next scheme indicator.
    for scheme in ("http://", "https://"):
        if scheme in candidate:
            candidate = candidate.split(scheme, 1)[0].rstrip("/")

    # Normalize host-prefixed paths (gitlab.com/owner/repo or github.com/owner/repo)
    for host in ("gitlab.com/", "github.com/"):
        if candidate.startswith(host):
            candidate = candidate[len(host):]

    candidate = candidate.strip("/")

    # Ensure standard owner/repo format, pick the first valid segment if extra text exists
    parts = [p for p in candidate.split("/") if p]
    if len(parts) >= 2:
        candidate = f"{parts[0]}/{parts[1]}"

    return candidate


def is_gitlab_repo(repo: str) -> bool:
    candidate = repo.strip()
    if candidate.startswith("https://") or candidate.startswith("http://"):
        return "gitlab.com" in urlparse(candidate).netloc
    return candidate.startswith("gitlab.com/")


def sanitize_ref(ref: str) -> str:
    return ref.replace("/", "_").replace(" ", "_")


CORE_MONITORED_SERVICES = ["users", "notifications", "orders", "products", "payments"]

DOWNSTREAM_MAPPING = {
    "users": ["orders", "payments", "products"],
    "orders": ["payments", "products"],
    "payments": [],
    "products": [],
    "notifications": [],
}


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
        suggestions.append(f"Impacted services/repositories detected: {', '.join(impacted_services)}")
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
    if impacted_services and ("orders" in impacted_services or "payments" in impacted_services or "products" in impacted_services):
        suggestions.append("Downstream core services flagged: run full e2e flow and regression for orders/payments/products.")
    if payload_response_changes:
        suggestions.append("Payload/response schema changes detected; verify dependent consumers still pass contract tests.")
    if changed_urls:
        suggestions.append("URL route modifications detected; update API gateway/consumer docs and integrations.")
    if impacted_core_services:
        suggestions.append(
            f"Monitored core services affected: {', '.join(impacted_core_services)}."
        )

    if risk["level"] in ("HIGH", "CRITICAL"):
        suggestions.append("Immediate action: block merge until regression pipelines pass, add/adjust tests, and issue cross-service rollout plan.")
    elif risk["level"] == "MEDIUM":
        suggestions.append("Action: prioritize end-to-end tests, manual validation of affected endpoints, and team communication.")
    else:
        suggestions.append("Action: continue with standard review and deploy checks; monitor impacted paths post-release.")

    return " ".join(suggestions)


def run_local_tests_for_service(service_dir: Path) -> Dict[str, Any]:
    result = {"service": str(service_dir), "status": "skipped", "message": "not found"}
    if not service_dir.exists() or not service_dir.is_dir():
        result["status"] = "missing"
        result["message"] = "directory not found"
        return result

    # prefer npm test for JS services
    test_cmd = ["npm", "test"]
    result["status"] = "failed"
    result["message"] = "unknown"
    try:
        proc = subprocess.run(test_cmd, cwd=service_dir, capture_output=True, text=True, timeout=600)
        result["output"] = proc.stdout + proc.stderr
        if proc.returncode == 0:
            result["status"] = "passed"
            result["message"] = "tests passed"
        else:
            result["status"] = "failed"
            result["message"] = f"exit {proc.returncode}"
    except FileNotFoundError:
        result["status"] = "missing"
        result["message"] = "npm not installed"
    except subprocess.TimeoutExpired:
        result["status"] = "failed"
        result["message"] = "timeout"
    except Exception as exc:
        result["status"] = "failed"
        result["message"] = str(exc)
    return result


async def compare_refs_safe(
    client: GitHubClient, repo: str, base_ref: str, target_ref: str, mode: str
) -> Dict[str, Any]:
    try:
        return await client.compare_refs(repo, base_ref, target_ref)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await ensure_ref_exists(client, repo, base_ref, "base ref", allow_tag=True, allow_branch=True)
            allow_target_tag = mode == "tag"
            await ensure_ref_exists(
                client,
                repo,
                target_ref,
                "target ref",
                allow_branch=not allow_target_tag,
                allow_tag=allow_target_tag,
            )
            raise RuntimeError(
                f"Compare endpoint for {mode} analysis returned 404; ensure the repo '{repo}' "
                f"exposes both base '{base_ref}' and target '{target_ref}'."
            ) from exc
        raise


async def ensure_ref_exists(
    client: GitHubClient,
    repo: str,
    ref: str,
    role: str,
    *,
    allow_branch: bool,
    allow_tag: bool,
) -> None:
    errors: List[str] = []
    if allow_branch:
        try:
            await client.get_branch(repo, ref)
            return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                errors.append(f"branch '{ref}'")
            else:
                raise
    if allow_tag:
        try:
            await client.get_tag_ref(repo, ref)
            return
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                errors.append(f"tag '{ref}'")
            else:
                raise
    if errors:
        desc = " and ".join(errors) if len(errors) == 1 else " / ".join(errors)
        raise RuntimeError(f"{role.capitalize()} {desc} does not exist in repository '{repo}'.")


async def main() -> None:
    args = parse_args()
    is_gitlab = is_gitlab_repo(args.repo)
    repo = normalize_repo(args.repo)
    settings = Settings()
    settings.report_dir = settings.report_dir
    summary_path = Path(settings.report_dir)
    summary_path.mkdir(parents=True, exist_ok=True)

    github_client = GitHubClient(settings)
    gitlab_client = GitLabClient(settings)
    pr_analyzer = PRAnalyzer(settings)
    dependency_scanner = DependencyScanner(github_client, settings)
    regression_runner = RegressionRunner(gitlab_client)
    risk_engine = RiskEngine()
    try:
        ai_summarizer = AISummarizer(settings)
    except RuntimeError:
        ai_summarizer = None  # type: ignore

    try:
        analysis_mode = "pr"
        target_ref = ""
        base_ref = None
        files: List[Dict[str, Any]] = []
        if args.pr is not None:
            if is_gitlab:
                pr_details = await gitlab_client.fetch_merge_request(repo, args.pr)
                files = await gitlab_client.list_changed_files(repo, args.pr)
                target_ref = f"MR #{args.pr}"
                if pr_details:
                    base_ref = pr_details.get("target_branch")
            else:
                pr_details = await github_client.fetch_pr(repo, args.pr)
                files = await github_client.list_changed_files(repo, args.pr)
                target_ref = f"PR #{args.pr}"
                if pr_details:
                    base_ref = pr_details.get("base", {}).get("ref")
        elif args.branch:
            analysis_mode = "branch"
            base_ref = args.base_ref
            target_ref = args.branch
            if is_gitlab:
                compare_payload = await gitlab_client.compare_refs(repo, base_ref, target_ref)
                files = [
                    {
                        "filename": d.get("new_path") or d.get("old_path"),
                        "additions": 0,
                        "deletions": 0,
                        "patch": d.get("diff", ""),
                    }
                    for d in compare_payload.get("diffs", [])
                ]
            else:
                compare_payload = await compare_refs_safe(
                    github_client, repo, base_ref, target_ref, analysis_mode
                )
                files = compare_payload.get("files", [])
        else:
            analysis_mode = "tag"
            base_ref = args.base_ref
            assert args.tag is not None
            target_ref = args.tag
            if is_gitlab:
                compare_payload = await gitlab_client.compare_refs(repo, base_ref, target_ref)
                files = [
                    {
                        "filename": d.get("new_path") or d.get("old_path"),
                        "additions": 0,
                        "deletions": 0,
                        "patch": d.get("diff", ""),
                    }
                    for d in compare_payload.get("diffs", [])
                ]
            else:
                compare_payload = await compare_refs_safe(
                    github_client, repo, base_ref, target_ref, analysis_mode
                )
                files = compare_payload.get("files", [])
        analysis = pr_analyzer.analyze(files)
        endpoints = analysis.endpoints
        changed_files = [info.get("filename", "") for info in files]

        scan_roots: List[Path] = []
        if args.scan_local_repos:
            for root_path in args.scan_local_repos:
                resolved = root_path if root_path.is_absolute() else (Path.cwd() / root_path).resolve()
                scan_roots.append(resolved)

        impacted_services: List[str] = []
        if endpoints:
            remote_impacted = await dependency_scanner.remote_impact(endpoints)
            impacted_services.extend(sorted(remote_impacted))

        predicted_downstream_services: Set[str] = set(impacted_services)
        for url in analysis.changed_urls:
            for key, downstream in DOWNSTREAM_MAPPING.items():
                if url.startswith(f"/{key}"):
                    predicted_downstream_services.update(downstream)

        predicted_downstream_services = sorted(predicted_downstream_services)

        local_matches = {}
        local_service_dirs: Set[Path] = set()

        for scan_root in scan_roots:
            service_roots: List[Path] = []
            if scan_root.exists():
                if (scan_root / "package.json").exists() or (scan_root / "package-lock.json").exists():
                    service_roots = [scan_root]
                else:
                    service_roots = [
                        child
                        for child in scan_root.iterdir()
                        if child.is_dir() and (child / "package.json").exists()
                    ]

            if endpoints and scan_root.exists():
                found = dependency_scanner.local_impact(endpoints, scan_root)
                for endpoint, paths in found.items():
                    local_matches.setdefault(endpoint, []).extend(paths)
                for endpoint, paths in found.items():
                    for filepath in paths:
                        matched_root = None
                        for root in service_roots:
                            try:
                                filepath.relative_to(root)
                                matched_root = root
                                break
                            except ValueError:
                                continue
                        if matched_root:
                            local_service_dirs.add(matched_root)
                        else:
                            local_service_dirs.add(scan_root)

            # Fallback: if no endpoint-driven impact detected for this root, use discovered service roots
            if not local_service_dirs and service_roots:
                local_service_dirs.update(service_roots)

        # Add impacted service names instead of raw endpoint values
        impacted_services.extend(sorted({d.name for d in local_service_dirs if d.name}))

        # Always expose impacted service names from local dirs when running tests
        if args.run_tests:
            for service_dir in sorted(local_service_dirs):
                service_name = service_dir.name
                if service_name and service_name not in impacted_services:
                    impacted_services.append(service_name)

        impacted_services = sorted(set(impacted_services))
        impacted_core_services = detect_core_service_impact(impacted_services)

        regression_results = {}
        regression_failures = []

        # Optional: run local tests in impacted services before pipeline trigger
        test_results = {}
        if args.run_tests and scan_roots:
            for service_dir in sorted(local_service_dirs):
                service_key = service_dir.name
                test_results[service_key] = run_local_tests_for_service(service_dir)

        for service in impacted_services:
            project_id = settings.gitlab_project_map.get(service)
            if not project_id:
                logger.warning("Missing GitLab mapping for %s", service)
                continue
            result = await regression_runner.trigger(project_id)
            status = result.get("status", "unknown")
            regression_results[service] = status
            if status != "success":
                regression_failures.append(service)

        risk = risk_engine.evaluate(
            files_changed=analysis.files_changed,
            sensitive_changes=analysis.sensitive_changes,
            api_change=pr_analyzer.api_change_detected(analysis.categories),
            db_model_change=pr_analyzer.database_change_detected(analysis.categories),
            impacted_repos=impacted_services,
            regression_failures=regression_failures,
            category_counts=analysis.category_counts,
            payload_response_changes=analysis.payload_response_changes,
            changed_urls=analysis.changed_urls,
        )

        solution_suggestion = build_solution_suggestion(
            risk=risk,
            impacted_services=impacted_services,
            downstream_services=predicted_downstream_services,
            sensitive_changes=analysis.sensitive_changes,
            api_change=pr_analyzer.api_change_detected(analysis.categories),
            db_model_change=pr_analyzer.database_change_detected(analysis.categories),
            impacted_core_services=impacted_core_services,
            payload_response_changes=analysis.payload_response_changes,
            changed_urls=sorted(analysis.changed_urls),
        )

        current_change_summary = (
            f"{analysis.files_changed} files changed, {analysis.total_additions} additions, "
            f"{analysis.total_deletions} deletions; sensitive files: {', '.join(analysis.sensitive_changes) or 'none'}; "
            f"endpoints: {', '.join(sorted(analysis.endpoints)) or 'none'}"
        )

        ai_summary = "LLM providers not configured."
        if ai_summarizer:
            context = {
                "analysis_mode": analysis_mode,
                "target_ref": target_ref,
                "base_ref": base_ref or "n/a",
                "repository": repo,
                "files_changed": str(analysis.files_changed),
                "current_change_summary": current_change_summary,
                "sensitive_changes": ", ".join(analysis.sensitive_changes) or "none",
                "endpoints": ", ".join(sorted(analysis.endpoints)) or "none",
                "impacted_services": ", ".join(impacted_services) or "none",
                "downstream_services": ", ".join(predicted_downstream_services) or "none",
                "impacted_core_services": ", ".join(impacted_core_services) or "none",
                "risk_score": str(risk["score"]),
                "risk_level": risk["level"],
                "suggested_solution": solution_suggestion,
            }
            if args.pr is not None:
                context["pr"] = str(args.pr)
            ai_summary = await ai_summarizer.summarize(context)
            if not ai_summary or ai_summary.startswith("LLM unavailable"):
                ai_summary = (
                    "LLM unavailable. Predicted downstream impacted services: "
                    f"{', '.join(predicted_downstream_services) or 'none'}. "
                    "Suggested actions: run contracts for impacted services, update URL mapping and payload/response adapters."
                )

        report = {
            "repository": repo,
            "analysis_mode": analysis_mode,
            "target_ref": target_ref,
            "base_ref": base_ref,
            "files_changed": analysis.files_changed,
            "sensitive_changes": analysis.sensitive_changes,
            "impacted_services": impacted_services,
            "downstream_impacted_services": predicted_downstream_services,
            "category_counts": analysis.category_counts,
            "payload_response_changes": analysis.payload_response_changes,
            "changed_urls": sorted(analysis.changed_urls),
            "predicted_downstream_services": predicted_downstream_services,
            "test_results": test_results if args.run_tests else {},
            "regression_results": regression_results,
            "risk_score": risk["score"],
            "risk_level": risk["level"],
            "impacted_core_services": impacted_core_services,
            "suggested_solution": solution_suggestion,
            "downstream_recommendation": solution_suggestion,
            "ai_summary": ai_summary,
            "local_scan": {
                str(p): [str(path) for path in paths]
                for p, paths in local_matches.items()
            },
        }

        target_identifier = sanitize_ref(target_ref or analysis_mode)
        report_file = summary_path / f"impact_report_{repo.replace('/', '_')}_{analysis_mode}_{target_identifier}.json"
        report_file.write_text(json.dumps(report, indent=2))

        # Also emit dedicated test-results JSON when run-tests is enabled
        test_report_file = None
        if args.run_tests and test_results:
            test_report_file = summary_path / f"test_results_{repo.replace('/', '_')}_{analysis_mode}_{target_identifier}.json"
            test_report_file.write_text(json.dumps(test_results, indent=2))

        logger.info("Generated risk report %s", report_file)
        if test_report_file:
            logger.info("Generated test report %s", test_report_file)
        print("Impact Report")
        print(f"Repository: {repo}")
        print(f"Analysis mode: {analysis_mode.capitalize()}")
        print(f"Target ref: {target_ref}")
        if base_ref:
            print(f"Base ref: {base_ref}")
        if args.pr is not None:
            print(f"PR #: {args.pr}")
        print(f"Risk Score: {risk['score']} ({risk['level']})")
        print(f"Impacted services: {', '.join(impacted_services) or 'none'}")
        print(f"Regression failures: {', '.join(regression_failures) or 'none'}")
        print(f"Suggested solution: {solution_suggestion}")
        print(f"Report saved: {report_file}")
    finally:
        await github_client.close()
        await gitlab_client.close()
        if ai_summarizer:
            await ai_summarizer.close()


if __name__ == "__main__":
    asyncio.run(main())
