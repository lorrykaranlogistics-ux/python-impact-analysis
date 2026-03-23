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
python3 -m venv .venv
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

You can also pass a full GitHub or GitLab repository URL (with or without `.git`) and the CLI will normalize it to the expected `owner/name` form.

For GitHub PR analysis:
```bash
python main.py --repo https://github.com/<org>/<repo> --pr 1
```

For GitLab merge request analysis:
```bash
python main.py --repo https://gitlab.com/sivamanismca/micro-service-users --pr 1

python main.py --repo ... --pr 1 --scan-local-repos users --run-tests


python main.py --repo https://gitlab.com/sivamanismca/micro-service-users --pr 1 --scan-local-repos users --run-tests



python main.py --repo https://gitlab.com/sivamanismca/micro-service-users  --pr 1 \
  --scan-local-repos ../micro-services/users ../micro-services/notifications ../micro-services/products ../micro-services/payments \
  --run-tests

```


```bash
python main.py \
  --repo https://gitlab.com/sivamanismca/micro-service-users \
  --pr 1 \
  --scan-local-repos \
    https://gitlab.com/sivamanismca/micro-service-notifications \
    https://gitlab.com/sivamanismca/micro-services/users \
    https://gitlab.com/sivamanismca/micro-services/products \
    https://gitlab.com/sivamanismca/micro-services/payments \
  --run-tests

```



Branch and tag analysis no longer requires an open PR. Provide the target ref and optional `--base-ref` (defaults to `main`):

```bash
python main.py --repo my-org/order-service --branch feature/awesome --base-ref main

python main.py --repo https://gitlab.com/sivamanismca/micro-service-usershttps://gitlab.com/sivamanismca/micro-service-users --branch feature/route --base-ref master

python main.py --repo my-org/order-service --tag v2.0.0 --base-ref main
```

Only one of `--pr`, `--branch`, or `--tag` can be supplied per run.

Optional local scan of service directories:

```bash
python main.py --repo my-org/orders --pr 142 --scan-local-repos ./microservices
```

Run tests in impacted local services before regression trigger:

```bash
python main.py --repo my-org/orders --pr 142 --scan-local-repos ./microservices --run-tests
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

## Mock microservice order workflow

The new `microservices` package demonstrates how an `OrderMicroserviceOrchestrator` can wire together HTTP-style API calls across
the mock services (`orders`, `inventory`, `payments`, `notifications`, `users`). Run the orchestration demo with:

```bash
python -m microservices
```

The orchestrator uses mock endpoints by default—any `mock://` prefixed service is handled locally with deterministic payloads and
logs each step. Override `DEFAULT_SERVICE_ENDPOINTS` when you want to point to real services or swap in HTTP clients for integration tests.
