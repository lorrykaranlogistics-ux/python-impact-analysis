from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from analysis.code_advisor import build_code_advice
from analysis.impact_report import (
    DOWNSTREAM_MAPPING,
    build_code_suggestions,
    build_solution_suggestion,
    detect_core_service_impact,
)
from github.pr_analyzer import PRAnalyzer
from risk.risk_engine import RiskEngine
from utils.file_parser import find_endpoints_in_directory
from config import Settings


GitDiffEntry = Dict[str, Any]


class GitCommandError(RuntimeError):
    pass


def run_git_command(args: Iterable[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise GitCommandError(proc.stderr.strip() or "git command failed")
    return proc.stdout


def parse_numstat(output: str) -> Dict[str, Tuple[int, int]]:
    stats: Dict[str, Tuple[int, int]] = {}
    for line in output.strip().splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        adds, deletes, path = parts
        try:
            stats[path] = (int(adds), int(deletes))
        except ValueError:
            stats[path] = (0, 0)
    return stats


def build_change_entries(patch: str, stats: Dict[str, Tuple[int, int]]) -> List[GitDiffEntry]:
    entries: List[GitDiffEntry] = []
    for section in patch.split("diff --git ")[1:]:
        lines = section.splitlines()
        if not lines:
            continue
        header = lines[0]
        match = re.match(r"a/(?P<a>.+)\s+b/(?P<b>.+)", header)
        if not match:
            continue
        filename = match.group("b")
        if filename == "/dev/null":
            filename = match.group("a")
        patch_body = "\n".join(lines[1:])
        adds, deletes = stats.get(filename, (0, 0))
        entries.append(
            {
                "filename": filename,
                "additions": adds,
                "deletions": deletes,
                "patch": patch_body,
            }
        )
    for path, (adds, deletes) in stats.items():
        if not any(entry["filename"] == path for entry in entries):
            entries.append({
                "filename": path,
                "additions": adds,
                "deletions": deletes,
                "patch": "",
            })
    return entries


def collect_diff_entries(repo_dir: Path, base_ref: str, target_ref: str) -> List[GitDiffEntry]:
    numstat = run_git_command(["diff", "--numstat", f"{base_ref}..{target_ref}"], repo_dir)
    stats = parse_numstat(numstat)
    patch = run_git_command(["diff", "-U0", f"{base_ref}..{target_ref}"], repo_dir)
    return build_change_entries(patch, stats)


@dataclass
class ImpactReport:
    repository: Path
    base_ref: str
    target_ref: str
    changed_files: List[str]
    sensitive_changes: List[str]
    endpoints: List[str]
    impacted_services: List[str]
    downstream_services: List[str]
    core_services: List[str]
    risk: Dict[str, Any]
    solution: str
    local_matches: Dict[str, List[str]]
    dependency_graph: Dict[str, List[str]]
    code_advice: List[Dict[str, object]]
    code_suggestions: List[str]


class GitBranchImpactAnalyzer:
    def __init__(
        self,
        repo_dir: Path,
        *,
        target_ref: str,
        base_ref: str = "main",
        scan_roots: Iterable[Path] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repo_dir = repo_dir
        self.target_ref = target_ref
        self.base_ref = base_ref
        self.scan_roots = list(scan_roots or [])
        self.settings = settings or Settings()
        self.pr_analyzer = PRAnalyzer(self.settings)
        self.risk_engine = RiskEngine()

    def analyze(self) -> ImpactReport:
        files = collect_diff_entries(self.repo_dir, self.base_ref, self.target_ref)
        analysis = self.pr_analyzer.analyze(files)
        endpoints = analysis.endpoints

        impacted_services: List[str] = [
            Path(info["filename"]).parts[0]
            for info in files
            if Path(info["filename"]).parts
        ]
        impacted_services = sorted({name for name in impacted_services if name})

        local_matches: Dict[str, List[Path]] = {}
        local_service_dirs: set[Path] = set()
        for scan_root in self.scan_roots:
            resolved = scan_root if scan_root.is_absolute() else (self.repo_dir / scan_root).resolve()
            if not resolved.exists():
                continue
            service_roots = self._find_service_roots(resolved)
            if endpoints:
                found = find_endpoints_in_directory(resolved, endpoints)
                for endpoint, paths in found.items():
                    local_matches.setdefault(endpoint, []).extend(paths)
                    for filepath in paths:
                        matched_root = self._find_containing_service(filepath, service_roots, resolved)
                        local_service_dirs.add(matched_root or resolved)
        impacted_services.extend(sorted({p.name for p in local_service_dirs if p.name}))
        impacted_services = sorted(set(impacted_services))

        downstream_services = sorted(set(self._predict_downstream(analysis.changed_urls, impacted_services)))
        core_services = detect_core_service_impact(impacted_services)

        risk = self.risk_engine.evaluate(
            files_changed=analysis.files_changed,
            sensitive_changes=analysis.sensitive_changes,
            api_change=self.pr_analyzer.api_change_detected(analysis.categories),
            db_model_change=self.pr_analyzer.database_change_detected(analysis.categories),
            impacted_repos=impacted_services,
            regression_failures=[],
            category_counts=analysis.category_counts,
            payload_response_changes=analysis.payload_response_changes,
            changed_urls=analysis.changed_urls,
        )

        solution = build_solution_suggestion(
            risk=risk,
            impacted_services=impacted_services,
            downstream_services=downstream_services,
            sensitive_changes=analysis.sensitive_changes,
            api_change=self.pr_analyzer.api_change_detected(analysis.categories),
            db_model_change=self.pr_analyzer.database_change_detected(analysis.categories),
            impacted_core_services=core_services,
            payload_response_changes=analysis.payload_response_changes,
            changed_urls=sorted(analysis.changed_urls),
        )

        code_suggestions = build_code_suggestions(
            changed_urls=sorted(analysis.changed_urls),
            payload_response_changes=analysis.payload_response_changes,
            impacted_services=impacted_services,
            sensitive_changes=analysis.sensitive_changes,
            endpoints=sorted(analysis.endpoints),
        )

        code_advice_entries = build_code_advice(
            local_matches,
            sorted(analysis.changed_urls),
            analysis.payload_response_changes,
            impacted_services,
        )

        graph = {service: DOWNSTREAM_MAPPING.get(service, []) for service in impacted_services}

        return ImpactReport(
            repository=self.repo_dir,
            base_ref=self.base_ref,
            target_ref=self.target_ref,
            changed_files=[info["filename"] for info in files],
            sensitive_changes=analysis.sensitive_changes,
            endpoints=sorted(analysis.endpoints),
            impacted_services=impacted_services,
            downstream_services=downstream_services,
            core_services=core_services,
            risk=risk,
            solution=solution,
            local_matches={
                endpoint: [str(path) for path in paths] for endpoint, paths in local_matches.items()
            },
            dependency_graph=graph,
            code_suggestions=code_suggestions,
            code_advice=[entry.to_dict() for entry in code_advice_entries],
        )

    def _find_service_roots(self, root: Path) -> List[Path]:
        if (root / "package.json").exists() or (root / "package-lock.json").exists():
            return [root]
        if not root.is_dir():
            return []
        return [child for child in root.iterdir() if child.is_dir() and (child / "package.json").exists()]

    def _find_containing_service(
        self, filepath: Path, service_roots: List[Path], fallback: Path
    ) -> Path:
        for root in service_roots:
            try:
                filepath.relative_to(root)
                return root
            except ValueError:
                continue
        return fallback

    @staticmethod
    def _predict_downstream(changed_urls: Iterable[str], impacted: List[str]) -> List[str]:
        downstream: set[str] = set(impacted)
        for url in changed_urls:
            for key, downstream_services in DOWNSTREAM_MAPPING.items():
                if url.startswith(f"/{key}"):
                    downstream.update(downstream_services)
        return sorted(downstream)


class GitHubClientPlaceholder:
    def __getattr__(self, name: str) -> Any:  # pragma: no cover - never called
        raise RuntimeError("GitBranchImpactAnalyzer does not initiate GitHub requests")
