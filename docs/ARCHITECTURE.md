# Architecture Document

## 1. System Overview
The system is an autonomous SDLC Orchestrator utilizing a GenAI model (google-genai) and GitHub integration.

## 2. Component Topology
- **Entrypoint:** orchestrator.py acts as the primary facade (re-exporting compatibility names).
- **Implementation Agents (orchestrator_core/implementation_agents.py):** PRESENT. Owns agent_implement_code and agent_generate_tests.
- **Review Agents (orchestrator_core/review_agents.py):** PRESENT. Owns agent_code_reviewer, agent_security_audit, build_coherence_summary, summarize_dependency_file.
- **Documentation Agents (orchestrator_core/documentation_agents.py):** PRESENT. Owns agent_update_architecture_doc, agent_update_user_manual, agent_generate_execution_report.
- **Failure Analysis Agents (orchestrator_core/failure_analysis_agents.py):** PRESENT. Owns agent_analyze_pipeline_failure.
- **Logging & Metadata (orchestrator_core/logging_metadata.py):** PRESENT. Owns write_local_log, write_transactional_metadata.
- **GitHub Operations (orchestrator_core/github_operations.py):** PRESENT. Owns fetch_issue, deploy_to_github, ensure_git_setup.
- **Core Orchestrator (orchestrator_core/):**
  - model_config.py: Ownership of model definitions (e.g., MODEL_LIGHT, MODEL_HEAVY).
  - runtime.py: Runtime client ownership (RuntimeClients, build_runtime_clients).
  - planning_agents.py: Planning agent ownership (agent_generate_acceptance_contract, agent_analyze_and_design).
  - response_parsing.py: Response parsing ownership.
  - testing_policy.py: Testing policy ownership.
  - contract_validation.py: Contract validation.
  - repository_context.py: Repository intelligence/context caching.
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
  - features/fatigue_calculator.py: Core domain logic.
- **Tests (tests/):**
  - Mirrors product components and isolates network calls. Test architecture verifies strict failures.
