from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    github_token: Optional[str] = Field(None, env="GITHUB_TOKEN")
    gitlab_token: Optional[str] = Field(None, env="GITLAB_TOKEN")
    gitlab_project_map: Dict[str, int] = Field(default_factory=dict, env="GITLAB_PROJECT_MAP")
    scan_repositories: List[str] = Field(default_factory=list, env="SCAN_REPOSITORIES")
    report_dir: str = Field("reports", env="REPORT_DIR")

    claude_api_key: Optional[str] = Field(None, env="CLAUDE_API_KEY")
    claude_api_url: Optional[HttpUrl] = Field(
        default="https://api.anthropic.com/v1/complete", env="CLAUDE_API_URL"
    )
    gemini_api_key: Optional[str] = Field(None, env="GEMINI_API_KEY")
    gemini_api_url: Optional[HttpUrl] = Field(
        default="https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro",
        env="GEMINI_API_URL",
    )
    llm_provider: Optional[str] = Field("auto", env="LLM_PROVIDER")

    sensitive_paths: List[str] = Field(
        default_factory=lambda: [
            "routes/",
            "controllers/",
            "models/",
            "schemas/",
            "dto/",
            "middleware/",
            "api/",
            "graphql/",
        ]
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
