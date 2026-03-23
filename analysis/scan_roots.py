from __future__ import annotations

import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, List, Tuple
from urllib.parse import quote_plus, urlparse, urlunparse

from subprocess import CalledProcessError

GIT_URL_PREFIXES = ("http://", "https://", "git@")


def is_remote_git_repo(spec: str) -> bool:
    return spec.startswith(GIT_URL_PREFIXES)


def _inject_token(url: str, github_token: str | None, gitlab_token: str | None) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    host = parsed.netloc.lower()
    token = None
    username = None
    if "gitlab.com" in host and gitlab_token:
        token = gitlab_token.strip()
        username = "oauth2"
    elif "github.com" in host and github_token:
        token = github_token.strip()
        username = "x-access-token"
    if token:
        safe_token = quote_plus(token)
        auth_netloc = f"{username}:{safe_token}@{parsed.netloc}"
        return urlunparse(parsed._replace(netloc=auth_netloc))
    return url


def _normalize_gitlab_services_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "gitlab.com" not in host:
        return None
    path = parsed.path
    match = re.search(r"/micro-services/([^/]+?)(\.git)?$", path)
    if not match:
        return None
    base = path[: match.start()]
    service = match.group(1)
    suffix = match.group(2) or ""
    fallback_path = f"{base}/micro-service-{service}{suffix}"
    if fallback_path == path:
        return None
    return urlunparse(parsed._replace(path=fallback_path))


def _attempt_clone(url: str, github_token: str | None, gitlab_token: str | None) -> Tuple[Path, TemporaryDirectory]:
    temp_dir = TemporaryDirectory(prefix="impact-scan-")
    auth_url = _inject_token(url, github_token, gitlab_token)
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", auth_url, temp_dir.name],
            check=True,
            capture_output=True,
            text=True,
        )
    except CalledProcessError as exc:
        temp_dir.cleanup()
        raise RuntimeError(f"Failed to clone remote repo {url}: {exc.stderr.strip()}") from exc
    return Path(temp_dir.name), temp_dir


def clone_remote_repo(url: str, github_token: str | None, gitlab_token: str | None) -> Tuple[Path, TemporaryDirectory]:
    try:
        return _attempt_clone(url, github_token, gitlab_token)
    except RuntimeError as exc:
        fallback_url = _normalize_gitlab_services_url(url)
        if fallback_url:
            try:
                return _attempt_clone(fallback_url, github_token, gitlab_token)
            except RuntimeError:
                pass
        raise exc


def resolve_scan_roots(
    specs: Iterable[str],
    github_token: str | None = None,
    gitlab_token: str | None = None,
) -> Tuple[List[Path], List[TemporaryDirectory]]:
    roots: List[Path] = []
    temp_dirs: List[TemporaryDirectory] = []
    for spec in specs:
        if is_remote_git_repo(spec):
            path, temp = clone_remote_repo(spec, github_token, gitlab_token)
            roots.append(path)
            temp_dirs.append(temp)
            continue
        candidate = Path(spec)
        if not candidate.is_absolute():
            candidate = candidate.resolve()
        roots.append(candidate)
    return roots, temp_dirs
