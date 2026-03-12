from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List
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
        type=Path,
        help="Optional local directory containing other services to scan",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="Base ref used when analyzing a branch or tag (default: main)",
    )
    return parser.parse_args()


def normalize_repo(repo: str) -> str:
    candidate = repo.strip()
    if candidate.endswith(".git"):
        candidate = candidate[: -4]
    if candidate.startswith("http://") or candidate.startswith("https://"):
        parsed = urlparse(candidate)
        candidate = parsed.path.lstrip("/")
    return candidate


def sanitize_ref(ref: str) -> str:
    return ref.replace("/", "_").replace(" ", "_")


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
            pr_details = await github_client.fetch_pr(repo, args.pr)
            files = await github_client.list_changed_files(repo, args.pr)
            target_ref = f"PR #{args.pr}"
            if pr_details:
                base_ref = pr_details.get("base", {}).get("ref")
        elif args.branch:
            analysis_mode = "branch"
            base_ref = args.base_ref
            target_ref = args.branch
            compare_payload = await compare_refs_safe(
                github_client, repo, base_ref, target_ref, analysis_mode
            )
            files = compare_payload.get("files", [])
        else:
            analysis_mode = "tag"
            base_ref = args.base_ref
            assert args.tag is not None
            target_ref = args.tag
            compare_payload = await compare_refs_safe(
                github_client, repo, base_ref, target_ref, analysis_mode
            )
            files = compare_payload.get("files", [])
        analysis = pr_analyzer.analyze(files)
        endpoints = analysis.endpoints
        impacted_services: List[str] = []
        if endpoints:
            remote_impacted = await dependency_scanner.remote_impact(endpoints)
            impacted_services.extend(sorted(remote_impacted))
        local_matches = {}
        if args.scan_local_repos and endpoints:
            local_matches = dependency_scanner.local_impact(endpoints, args.scan_local_repos)
            impacted_services.extend(sorted(set(local_matches.keys())))
        impacted_services = sorted(set(impacted_services))

        regression_results = {}
        regression_failures = []
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
        )

        ai_summary = "LLM providers not configured."
        if ai_summarizer:
            context = {
                "analysis_mode": analysis_mode,
                "target_ref": target_ref,
                "base_ref": base_ref or "n/a",
                "repository": repo,
                "files_changed": str(analysis.files_changed),
                "sensitive_changes": ", ".join(analysis.sensitive_changes) or "none",
                "impacted_services": ", ".join(impacted_services) or "none",
                "risk_score": str(risk["score"]),
                "risk_level": risk["level"],
            }
            if args.pr is not None:
                context["pr"] = str(args.pr)
            ai_summary = await ai_summarizer.summarize(context)

        report = {
            "repository": repo,
            "analysis_mode": analysis_mode,
            "target_ref": target_ref,
            "base_ref": base_ref,
            "files_changed": analysis.files_changed,
            "sensitive_changes": analysis.sensitive_changes,
            "impacted_services": impacted_services,
            "regression_results": regression_results,
            "risk_score": risk["score"],
            "risk_level": risk["level"],
            "ai_summary": ai_summary,
            "local_scan": {
                str(p): [str(path) for path in paths]
                for p, paths in local_matches.items()
            },
        }

        target_identifier = sanitize_ref(target_ref or analysis_mode)
        report_file = summary_path / f"impact_report_{repo.replace('/', '_')}_{analysis_mode}_{target_identifier}.json"
        report_file.write_text(json.dumps(report, indent=2))

        logger.info("Generated risk report %s", report_file)
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
        print(f"Report saved: {report_file}")
    finally:
        await github_client.close()
        await gitlab_client.close()
        if ai_summarizer:
            await ai_summarizer.close()


if __name__ == "__main__":
    asyncio.run(main())
