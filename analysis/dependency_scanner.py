from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Set

from ..config import Settings
from ..github.github_client import GitHubClient
from ..utils.file_parser import find_endpoints_in_directory


class DependencyScanner:
    def __init__(self, github_client: GitHubClient, settings: Settings):
        self.github_client = github_client
        self.settings = settings

    async def remote_impact(self, endpoints: Iterable[str]) -> Set[str]:
        impacted: Set[str] = set()
        for repo in self.settings.scan_repositories:
            for endpoint in endpoints:
                items = await self.github_client.search_code(repo, endpoint)
                if items:
                    impacted.add(repo)
        return impacted

    def local_impact(self, endpoints: Iterable[str], root: Path) -> Dict[str, List[Path]]:
        return find_endpoints_in_directory(root, endpoints)
