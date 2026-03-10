from __future__ import annotations

from typing import Any, Dict

import httpx

from ..config import Settings


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

    async def close(self) -> None:
        await self.client.aclose()
