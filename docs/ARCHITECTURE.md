# Architecture Document

## 1. System Overview
The system is an autonomous SDLC Orchestrator utilizing a GenAI model (google-genai) and GitHub integration.

## 2. Component Topology
- **Entrypoint:** orchestrator.py acts as the primary facade. It contains the orchestrator logic including gent_implement_code and gent_generate_tests. (Note: M10 future module implementation_agents.py is ABSENT).
- **Core Orchestrator (orchestrator_core/):**
  - model_config.py: Ownership of model definitions (e.g., MODEL_LIGHT, MODEL_HEAVY).
  - untime.py: Runtime client ownership (RuntimeClients, uild_runtime_clients).
  - planning_agents.py: Planning agent ownership (gent_generate_acceptance_contract, gent_analyze_and_design).
  - esponse_parsing.py: Response parsing ownership.
  - 	esting_policy.py: Testing policy ownership.
  - contract_validation.py: Contract validation.
  - epository_context.py: Repository intelligence/context caching.
  - prompt_budget.py, context_budget.py, prompt_context.py: Prompt budgeting and context generation.
  - quality_gates.py: Quality gates implementation (ruff, mypy, vulture, pytest).
  - schemas.py: Schema ownership (using Pydantic).
  - import_graph.py: Import-direction constraints and graph analysis.
  - ast_utils.py: Serializes AST nodes and extracts top-level signatures safely via static analysis.
  - exceptions.py: Ownership of custom exceptions (e.g., ContractGenerationError).
  - paths.py: Safe path resolution enforcing repository boundary security.
  - project_config.py: Extracts dependencies from standard Python config files (pyproject.toml, etc.) using safe AST parsers.
- **Product Domain (src/):**
  - data/besoccer_client.py: External integrations.
  - data/cement_dictionary.py: Normalization.
  - eatures/fatigue_calculator.py: Core domain logic.
- **Tests (	ests/):**
  - Mirrors product components and isolates network calls. Test architecture verifies strict failures.
