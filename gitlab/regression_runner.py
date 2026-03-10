from __future__ import annotations

from typing import Dict, List

from .gitlab_client import GitLabClient


class RegressionRunner:
    def __init__(self, client: GitLabClient):
        self.client = client

    async def trigger(self, project_id: int, ref: str = "main") -> Dict[str, str]:
        payload = await self.client.trigger_pipeline(project_id, ref)
        pipeline_id = payload.get("id")
        if not pipeline_id:
            return {"status": "unknown", "logs": "Pipeline id missing."}
        pipeline = await self.client.get_pipeline(project_id, pipeline_id)
        status = pipeline.get("status", "unknown")
        return {
            "status": status,
            "web_url": pipeline.get("web_url", ""),
            "logs": pipeline.get("detailed_status", {}).get("details_path", ""),
        }
