from __future__ import annotations

import subprocess
from pathlib import Path

from analysis.git_branch_impact import GitBranchImpactAnalyzer


def _run_git(cmd, cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def _prepare_repo(tmp_path: Path) -> Path:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _run_git(["git", "init", "-b", "main"], repo_dir)
    _run_git(["git", "config", "user.email", "test@example.com"], repo_dir)
    _run_git(["git", "config", "user.name", "Test"], repo_dir)
    (repo_dir / "README.md").write_text("baseline")
    _run_git(["git", "add", "README.md"], repo_dir)
    _run_git(["git", "commit", "-m", "initial"], repo_dir)
    _run_git(["git", "checkout", "-b", "feature"] , repo_dir)
    return repo_dir


def test_git_branch_impact_detects_users_service(tmp_path: Path) -> None:
    repo_dir = _prepare_repo(tmp_path)
    services_dir = repo_dir / "services"
    users_dir = services_dir / "users"
    users_dir.mkdir(parents=True)
    (users_dir / "package.json").write_text("{}")
    api_file = users_dir / "api.py"
    api_file.write_text("""
def register_user():
    return {"path": "/users/register", "payload": {"name": "string"}}
""")
    _run_git(["git", "add", "services/users"], repo_dir)
    _run_git(["git", "commit", "-m", "add users api"], repo_dir)

    analyzer = GitBranchImpactAnalyzer(
        repo_dir,
        target_ref="feature",
        scan_roots=[services_dir],
    )
    report = analyzer.analyze()

    assert "services/users/api.py" in report.changed_files
    assert "users" in report.impacted_services
    assert "/users/register" in report.endpoints
    assert report.core_services == ["users"]
    assert report.code_suggestions
    assert "users" in " ".join(report.code_suggestions)
    assert report.code_advice
    first_advice = report.code_advice[0]
    assert first_advice["file"].endswith("api.py")
    assert "/users/register" in first_advice["reason"]
