# Impact Analysis Agent

A Python 3.11+ CLI tool that analyzes GitHub pull requests, detects downstream microservice impact, triggers GitLab regression runs, and produces a risk/risk report with optional AI summaries from Claude or Gemini.

## Features
- Fetches GitHub PR metadata and classifies file changes (API/database/UI/config/test).
- Detects sensitive paths and endpoint diffs that can impact other repositories.
- Scans other GitHub repositories (configurable list) via the code search API.
- Optional local directory scan for endpoint usage.
- Triggers GitLab regression pipelines for impacted services.
- Computes a configurable risk score and risk level.
- Produces an optional AI-powered summary using Claude or Gemini providers.
- Saves a JSON report per execution and prints a short console summary.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration
Create a `.env` file or set environment variables directly. The agent reads the following values:

| Variable | Description |
| --- | --- |
| `GITHUB_TOKEN` | (optional) GitHub PAT to avoid rate limits. |
| `GITLAB_TOKEN` | GitLab trigger token used to post pipelines. |
| `GITLAB_PROJECT_MAP` | JSON object mapping service identifiers to GitLab project IDs, e.g. `{"payment-service": 12345}`. |
| `SCAN_REPOSITORIES` | Comma-separated GitHub repositories to scan for impacted services, e.g. `org/payment-service,org/notifications`. |
| `REPORT_DIR` | Directory to emit JSON reports (default: `reports`). |
| `CLAUDE_API_KEY` | API key for Claude. |
| `CLAUDE_API_URL` | Optional override for the Claude endpoint. |
| `GEMINI_API_KEY` | API key for Gemini. |
| `GEMINI_API_URL` | Optional override for the Gemini endpoint. |

`GITLAB_PROJECT_MAP` and `SCAN_REPOSITORIES` expect JSON/CSV values; you can rely on `dotenv` or inject via your runtime environment.

## Usage

```bash
python main.py --repo my-org/order-service --pr 142
```

Optional local scan of service directories:

```bash
python main.py --repo my-org/orders --pr 142 --scan-local-repos ./microservices
```

The CLI prints the summary and writes the JSON file into the configured `reports/` directory.

## Testing

```bash
pytest
```

## Extending
- Add additional sensitive patterns via `config.py`.
- Plug in different LLM providers by extending `llm/base_llm.py`.
- Enhance dependency scanning (e.g., parse AST), or map GitLab projects dynamically.
