from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from ..config import Settings


class GitHubClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if settings.github_token:
            headers["Authorization"] = f"Bearer {settings.github_token}"
        self.client = httpx.AsyncClient(base_url="https://api.github.com", timeout=30.0, headers=headers)

    async def fetch_pr(self, repo: str, pr_number: int) -> Dict[str, Any]:
        response = await self.client.get(f"/repos/{repo}/pulls/{pr_number}")
        response.raise_for_status()
        return response.json()

    async def list_changed_files(self, repo: str, pr_number: int) -> List[Dict[str, Any]]:
        all_files: List[Dict[str, Any]] = []
        page = 1
        while True:
            response = await self.client.get(
                f"/repos/{repo}/pulls/{pr_number}/files", params={"per_page": 100, "page": page}
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            all_files.extend(batch)
            page += 1
        return all_files

    async def search_code(self, repo: str, query: str) -> List[Dict[str, Any]]:
        params = {"q": f"{query} repo:{repo}", "per_page": 10}
        response = await self.client.get("/search/code", params=params)
        response.raise_for_status()
        return response.json().get("items", [])

    async def close(self) -> None:
        await self.client.aclose()
