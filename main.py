from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Dict, List

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
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument(
        "--scan-local-repos",
        type=Path,
        help="Optional local directory containing other services to scan",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
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
        pr_details = await github_client.fetch_pr(args.repo, args.pr)
        files = await github_client.list_changed_files(args.repo, args.pr)
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
                "repository": args.repo,
                "pr": str(args.pr),
                "files_changed": str(analysis.files_changed),
                "sensitive_changes": ", ".join(analysis.sensitive_changes) or "none",
                "impacted_services": ", ".join(impacted_services) or "none",
                "risk_score": str(risk["score"]),
                "risk_level": risk["level"],
            }
            ai_summary = await ai_summarizer.summarize(context)

        report = {
            "repository": args.repo,
            "pr_number": args.pr,
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

        report_file = summary_path / f"impact_report_{args.repo.replace('/', '_')}_{args.pr}.json"
        report_file.write_text(json.dumps(report, indent=2))

        logger.info("Generated risk report %s", report_file)
        print("PR Impact Report")
        print(f"Repository: {args.repo}")
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
