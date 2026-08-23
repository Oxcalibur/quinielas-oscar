# User Manual

## Overview
This system orchestrates the SDLC using autonomous agents.

## Invocation and CLI
**Main Orchestrator (orchestrator.py)**
- --issue <int>: Required. The issue number to process.

**Product Owner Agent (po_agent.py)**
- --requirements <path>: Path to functional specification.
- --approve-epic <int>: Epic issue number to verify and deploy.
- --refine-issue <int>: Issue number to refine based on technical feedback.
- --pm-report <str>: Post-Mortem report text for refinement.

## Environment Variables
- GITHUB_TOKEN: For PyGithub integration.
- GEMINI_API_KEY: For Google GenAI interactions.
- REPO_OWNER: Required. Defines the owner of the target GitHub repository for integrations.
- REPO_NAME: Required. Defines the name of the target GitHub repository.
- BYPASS_SSL_VERIFY: Optional. If set to "true", disables TLS/SSL certificate verification for network clients (exception/debug behavior).

## Expected Context & Quality Gates
The system requires a strict repository context. When an issue is run, it goes through mandatory quality gates:
- **Pytest** for testing.
- **Ruff** for linting.
- **Mypy** for typing.
- **Vulture** for dead code analysis.

## Outputs
- **Runs Registry:** Execution outputs are logged structurally to docs/metadata/runs_registry.json.
- Failures exhibit fail-fast behavior.
