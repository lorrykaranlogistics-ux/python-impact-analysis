from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote_plus

import httpx

from config import Settings


class GitLabClient:
    BASE_URL = "https://gitlab.com/api/v4"

    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {
            "Content-Type": "application/json",
        }
        if settings.gitlab_token:
            headers["PRIVATE-TOKEN"] = settings.gitlab_token
        self.client = httpx.AsyncClient(base_url=self.BASE_URL, timeout=30.0, headers=headers)

    async def trigger_pipeline(self, project_id: int, ref: str = "main") -> Dict[str, Any]:
        data = {
            "ref": ref,
        }
        response = await self.client.post(f"/projects/{project_id}/trigger/pipeline", json=data)
        response.raise_for_status()
        return response.json()

    async def get_pipeline(self, project_id: int, pipeline_id: int) -> Dict[str, Any]:
        response = await self.client.get(f"/projects/{project_id}/pipelines/{pipeline_id}")
        response.raise_for_status()
        return response.json()

    async def fetch_merge_request(self, repo: str, mr_iid: int) -> Dict[str, Any]:
        project = quote_plus(repo)
        response = await self.client.get(f"/projects/{project}/merge_requests/{mr_iid}")
        response.raise_for_status()
        return response.json()

    async def list_changed_files(self, repo: str, mr_iid: int) -> List[Dict[str, Any]]:
        project = quote_plus(repo)
        response = await self.client.get(f"/projects/{project}/merge_requests/{mr_iid}/changes")
        response.raise_for_status()
        payload = response.json()
        changes = payload.get("changes", [])
        files = []
        for change in changes:
            files.append(
                {
                    "filename": change.get("new_path") or change.get("old_path"),
                    "additions": 0,
                    "deletions": 0,
                    "patch": change.get("diff", ""),
                }
            )
        return files

    async def compare_refs(self, repo: str, from_ref: str, to_ref: str) -> Dict[str, Any]:
        project = quote_plus(repo)
        response = await self.client.get(
            f"/projects/{project}/repository/compare",
            params={"from": from_ref, "to": to_ref},
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self.client.aclose()
