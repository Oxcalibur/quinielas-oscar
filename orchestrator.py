"""
Orquestador SDLC de Agentes Autónomos con Refactorización Dinámica y Calidad Estática (Versión 2026)
Optimizado para decisiones dinámicas de arquitectura modular libre, Docs-as-Code,
análisis estático contra código muerto (Vulture) y linter (Ruff),
y Git flow con Run ID y registro transaccional JSON de alta trazabilidad.
Incluye un Agente Clínico Post-Mortem y Reflexión Multinivel Integral para auto-corrección estructural.
"""

# 1. PARCHE DE SEGURIDAD SSL INICIAL
# (Se movió a build_runtime_clients para no afectar la importación estática)

import ast
import configparser
import datetime
import fnmatch
import hashlib
import json
import logging
import os
import re
import subprocess
import sys

from dataclasses import dataclass
from dotenv import load_dotenv

# Constante para evitar cortes en el renderizado de la UI del chat y formatear Prompts

# =====================================================================
# CONFIGURACIÓN DEL LOGGER
# =====================================================================
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s')

# =====================================================================
# FUNCIONES AUXILIARES PURAS (no requieren credenciales ni red)
# =====================================================================
from orchestrator_core.model_config import MODEL_LIGHT
from orchestrator_core.response_parsing import MD_FENCE, extract_code
from orchestrator_core.testing_policy import resolve_mocking_instruction
from orchestrator_core.ast_utils import (
    serialize_ast_signature,
    extract_ast_signatures,
)




from github import Auth, Github
from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError
from typing import Dict, List, Any, Optional, Tuple, Literal
from orchestrator_core.semantic_validators import validate_semantic_fidelity
from orchestrator_core.runtime import RuntimeClients, build_runtime_clients

# --- CONFIGURACION DE MODELOS GEMINI 3 (VIGENCIA 2026) ---
from orchestrator_core.model_config import MODEL_HEAVY   # Razonamiento complejo, refactorizacion estructural y auditorias

# =====================================================================
# FUNCIONES AUXILIARES DE ANÁLISIS
# =====================================================================
from orchestrator_core.project_config import (
    is_test_file,
    parse_pyproject,
    parse_requirements,
    parse_pipfile,
    parse_poetry_lock,
    parse_setup_cfg,
    parse_setup_py,
)

# =====================================================================
# GESTOR DE CONTEXTO HIBRIDO (ANALISIS ESTATICO DE ARCHIVOS CON AST)
# =====================================================================
from orchestrator_core.import_graph import (
    extract_imported_modules,
    resolve_imported_files,
)

from orchestrator_core.repository_context import RepositoryContextManager

# Instancia global de contexto
# =====================================================================
# ESQUEMAS PYDANTIC PARA REFACTORIZACION Y DISENO DINAMICO LIBRE
# =====================================================================
from orchestrator_core.schemas import (
    FileAction,
    ContextRequest,
    ProjectDesign,
    ReviewFinding,
    CodeReviewResult,
    QualityGatePlan,
    PythonQualityPolicy,
    PythonProjectConfiguration,
    SecurityAuditResult,
    ArchitectureConflict,
    PythonFileSummary,
    RepositoryIndexCache,
    RequiredCall,
    PreservedBehavior,
    FileContract,
    ContextBudget,
    RepositoryContext,
    AcceptanceContract,
    GateResult,
    ContractCapability,
)






from orchestrator_core.prompt_budget import (
    PreflightError,
    PromptBudget,
    PromptPayload,
    ensure_prompt_fits,
    add_required_or_fail,
    fit_optional_text,
)












# Custom Exceptions

from orchestrator_core.exceptions import ContractGenerationError



_VALID_VALIDATION_METHODS = {"protected_test", "required_test", "semantic_reviewer"}








# =====================================================================
# REGISTRO DE CAPACIDADES DEL VALIDADOR DE CONTRATOS
# =====================================================================
_SUPPORTED_AST_CONSTRUCTS = {"continue", "pass"}
from orchestrator_core.contract_validation import (
    _SUPPORTED_CODE_PATTERNS,
    _SUPPORTED_STRUCTURE_CHECKS,
    validate_relevant_context_files,
    canonicalize_testing_technique,
    validate_contract_consistency,
    _create_file_contract,
    _check_forbidden_constructs,
    _check_exports,
    _check_tests,
    _check_imports,
    _check_patterns,
    _check_calls,
    _check_structures,
    _get_decorator_name,
    _check_decorators,
    _check_preserved_signatures,
    _check_testing_techniques,
    validate_contractual_ast,
    validate_design,
    validate_generated_manifest,
    validate_final_state,
)


_SUPPORTED_TESTING_TECHNIQUES = {"unittest.mock.patch", "pytest-mock", "mocker", "monkeypatch"}
_SUPPORTED_QUALITY_TOOLS = {"mypy", "pytest", "unittest", "ruff", "vulture"}

_validator_registry = {
    "forbidden_constructs": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_forbidden_constructs", supported_values=_SUPPORTED_AST_CONSTRUCTS),
    "required_patterns": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_patterns", supported_values=_SUPPORTED_CODE_PATTERNS),
    "required_structures": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_structures", supported_values=_SUPPORTED_STRUCTURE_CHECKS),
    "required_final_files": ContractCapability(validation_type="pipeline", implemented=True, validator_name="validate_contract_consistency"),
    "required_new_files": ContractCapability(validation_type="pipeline", implemented=True, validator_name="validate_contract_consistency"),
    "required_modified_files": ContractCapability(validation_type="pipeline", implemented=True, validator_name="validate_contract_consistency"),
    "required_deleted_files": ContractCapability(validation_type="pipeline", implemented=True, validator_name="validate_contract_consistency"),
    "preserved_files": ContractCapability(validation_type="pipeline", implemented=True, validator_name="validate_contract_consistency"),
    "relevant_context_files": ContractCapability(validation_type="pipeline", implemented=True, validator_name="validate_relevant_context_files"),
    "required_tests": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_tests"),
    "protected_tests": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_tests"),
    "preserved_signatures": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_preserved_signatures"),
    "required_exports": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_exports"),
    "required_imports": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_imports"),
    "forbidden_imports": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_imports"),
    "required_calls": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_calls"),
    "required_decorators": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_decorators"),
    "forbidden_test_names": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_tests"),
    "preserved_behaviors": ContractCapability(validation_type="reviewer", implemented=True, validator_name="agent_code_reviewer"),
    "required_quality_tools": ContractCapability(validation_type="pipeline", implemented=True, validator_name="_derive_gate_plan"),
    "forbidden_quality_tools": ContractCapability(validation_type="pipeline", implemented=True, validator_name="_derive_gate_plan"),
    "required_testing_techniques": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_testing_techniques", supported_values=_SUPPORTED_TESTING_TECHNIQUES),
    "forbidden_testing_techniques": ContractCapability(validation_type="ast", implemented=True, validator_name="_check_testing_techniques", supported_values=_SUPPORTED_TESTING_TECHNIQUES),
}



def validate_contract_capabilities(contract: AcceptanceContract, registry: dict) -> tuple[bool, list[str]]:
    """
    Valida que el contrato de aceptación solo use reglas y constructos
    soportados por el motor de validación AST.
    """
    errors = []

    # Reject contradictory quality tool declarations
    contradictory = set(t.lower() for t in contract.required_quality_tools) & set(t.lower() for t in contract.forbidden_quality_tools)
    for tool in contradictory:
        errors.append(f"Contrato inconsistente: '{tool}' aparece en required_quality_tools y forbidden_quality_tools al mismo tiempo.")

    required_frameworks = {
        tool.lower()
        for tool in contract.required_quality_tools
        if tool.lower() in {"pytest", "unittest"}
    }

    if len(required_frameworks) > 1:
        errors.append(
            "Contrato inconsistente: no se pueden requerir "
            "'pytest' y 'unittest' simultáneamente."
        )

    required_techniques_canonical = {
        canonicalize_testing_technique(t)
        for t in contract.required_testing_techniques
    }

    forbidden_techniques_canonical = {
        canonicalize_testing_technique(t)
        for t in contract.forbidden_testing_techniques
    }

    contradictory_techniques = required_techniques_canonical & forbidden_techniques_canonical
    for technique in contradictory_techniques:
        errors.append(f"Contrato inconsistente: la técnica '{technique}' aparece en required y forbidden al mismo tiempo.")

    implied_framework = None
    pytest_only_techniques = {"pytest-mock", "monkeypatch"}
    if required_techniques_canonical & pytest_only_techniques:
        implied_framework = "pytest"

    explicit_framework = None
    required_tools_lower = {t.lower() for t in contract.required_quality_tools}
    if "pytest" in required_tools_lower:
        explicit_framework = "pytest"
    elif "unittest" in required_tools_lower:
        explicit_framework = "unittest"

    if explicit_framework == "unittest" and implied_framework == "pytest":
        errors.append("Contrato inconsistente: requiere 'unittest' pero también exige técnicas incompatibles (pytest-mock o monkeypatch).")

    forbidden_tools_lower = {tool.lower() for tool in contract.forbidden_quality_tools}
    if implied_framework and implied_framework in forbidden_tools_lower:
        errors.append(f"El contrato exige técnicas que requieren '{implied_framework}', pero ese framework está prohibido.")

    def _get_supported(key: str) -> set:
        cap = registry.get(key)
        if isinstance(cap, ContractCapability):
            return cap.supported_values
        return set()

    # Check for specific unsupported values within supported fields
    for path_glob, constructs in contract.forbidden_constructs.items():
        for construct in constructs:
            if construct not in _get_supported("forbidden_constructs"):
                errors.append(f"Contrato usa un 'forbidden_construct' no soportado: '{construct}' en '{path_glob}'. Soportados: {sorted(list(_get_supported('forbidden_constructs')))}")

    for path_glob, patterns in contract.required_patterns.items():
        for pattern in patterns:
            if pattern not in _get_supported("required_patterns"):
                errors.append(f"Contrato usa un 'required_pattern' no soportado: '{pattern}' en '{path_glob}'. Soportados: {sorted(list(_get_supported('required_patterns')))}")

    for path_glob, structures in contract.required_structures.items():
        for var_name, check_type in structures.items():
            if check_type not in _get_supported("required_structures"):
                errors.append(f"Contrato usa un 'required_structure' check no soportado: '{check_type}' para '{var_name}' en '{path_glob}'. Soportados: {sorted(list(_get_supported('required_structures')))}")

    # Validate supported values for testing techniques
    supported_techniques = _get_supported("required_testing_techniques")
    for tech in contract.required_testing_techniques:
        if tech not in supported_techniques:
            errors.append(f"Contrato usa 'required_testing_technique' no soportada: '{tech}'. Soportadas: {sorted(supported_techniques)}")
    for tech in contract.forbidden_testing_techniques:
        if tech not in supported_techniques:
            errors.append(f"Contrato usa 'forbidden_testing_technique' no soportada: '{tech}'. Soportadas: {sorted(supported_techniques)}")

    # Check for entire fields that are not supported by the registry
    for field in contract.model_fields:
        field_value = getattr(contract, field)
        if field_value:  # Only report if the unsupported field is actually used
            capability = registry.get(field)
            if capability is None:
                errors.append(f"Contrato usa un campo no soportado por el validador: '{field}'.")
            elif not capability.implemented:
                errors.append(f"La capacidad de validación para '{field}' aún no está implementada en el orquestador.")
            elif capability.validator_name and capability.validator_name not in globals():
                errors.append(f"Validador '{capability.validator_name}' no existe para el campo '{field}'.")

    # Validate quality tools against the supported set
    for tool in contract.required_quality_tools:
        if tool.lower() not in _SUPPORTED_QUALITY_TOOLS:
            errors.append(f"Contrato requiere herramienta de calidad no soportada: '{tool}'. Soportadas: {sorted(_SUPPORTED_QUALITY_TOOLS)}")
    for tool in contract.forbidden_quality_tools:
        if tool.lower() not in _SUPPORTED_QUALITY_TOOLS:
            errors.append(f"Contrato prohíbe herramienta de calidad no conocida: '{tool}'. Conocidas: {sorted(_SUPPORTED_QUALITY_TOOLS)}")

    # Validate preserved_behaviors governance
    for pb in contract.preserved_behaviors:
        errors.extend(pb.validate_governance(contract))

    return not errors, errors



from orchestrator_core.implementation_agents import agent_implement_code, agent_generate_tests
from orchestrator_core.planning_agents import agent_generate_acceptance_contract, agent_analyze_and_design


# =====================================================================
# FUNCION DE LOGS LOCALES Y METADATOS TRANSACCIONALES
# =====================================================================


def run_orchestrator(issue_id: int, github_token: str | None = None, runtime: RuntimeClients | None = None):
    run_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    logging.info(f"=== INICIANDO ORQUESTADOR (Run ID: {run_id}) PARA ISSUE #{issue_id} ===")

    if not runtime:
        runtime = build_runtime_clients()

    run_log_dir = os.path.join(".agent-runs", run_id)
    os.makedirs(run_log_dir, exist_ok=True)

    run_pipeline(issue_id, run_id, run_log_dir, runtime)



# =====================================================================
# FUNCION DE ANALISIS ESTATICO DE CALIDAD (RUFF AUTO-FIX Y VULTURE BLINDADO)
# =====================================================================
from typing import Collection

from orchestrator_core.quality_gates import (
    run_static_analysis,
    reload_code_after_ruff,
    validate_code_quality,
    parse_compiler_output,
    build_mypy_scope,
    run_mypy,
    _derive_gate_plan,
    validate_testing_policy_compatibility,
    run_local_tests,
    base_preflight,
    tool_preflight,
)



# =====================================================================
# CAPA DE VALIDACIÓN DE CALIDAD DE CÓDIGO (NUEVO)
# =====================================================================





















from orchestrator_core.paths import resolve_safe_path

# =====================================================================
# FASES DEL PIPELINE DE ARQUITECTURA EVOLUTIVA
# =====================================================================



from orchestrator_core.context_budget import (
    estimate_repository_context_tokens,
)

from orchestrator_core.prompt_context import PromptContextBuilder
from orchestrator_core.review_agents import agent_code_reviewer, agent_security_audit
from orchestrator_core.documentation_agents import agent_update_architecture_doc, agent_update_user_manual, agent_generate_execution_report
from orchestrator_core.failure_analysis_agents import agent_analyze_pipeline_failure
from orchestrator_core.logging_metadata import write_local_log, write_transactional_metadata
from orchestrator_core.github_operations import fetch_issue, deploy_to_github, ensure_git_setup, _sanitize_staging_area












# =====================================================================
# AGENTE CLÍNICO DE DIAGNÓSTICO DE FALLOS CON GOBERNANZA AUTOMATIZADA
# =====================================================================


# =====================================================================
# AGENTE DE REVISIÓN DE CÓDIGO (NUEVO)
# =====================================================================




# =====================================================================
# GIT FLOW DE ALTA TRAZABILIDAD CON RUN ID
# =====================================================================


def materialize_cached_files(generated_files: dict[str, str], feedback_dict: dict[str, str], context_manager: "RepositoryContextManager") -> None:
    logging.info("Restaurando archivos cacheados que pasaron la validación...")
    for path, code in generated_files.items():
        if path in feedback_dict:
            continue

        try:
            safe_path = resolve_safe_path(".", path)
            directory = os.path.dirname(safe_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as file:
                file.write(code)
        except ValueError as e:
            logging.error(f"Error de seguridad al materializar archivo cacheado: {e}")
# =====================================================================
# COORDINADOR DEL WORKFLOW CENTRAL UNIFICADO
# =====================================================================


def handle_pipeline_failure(
    issue_id: int,
    title: str,
    error_msg: str,
    run_log_dir: str,
    runtime: RuntimeClients,
    pipeline_exc: Exception | None = None,
    gate_results: list = None,
    design: dict = None,
    generated_files: dict = None,
    issue_description: str = None
) -> None:
    """Centraliza la gestión de fallos catastróficos del pipeline."""
    flat_gates: list[GateResult] = []
    if gate_results:
        for item in gate_results:
            if isinstance(item, list):
                flat_gates.extend(item)
            else:
                flat_gates.append(item)
    logging.exception(f"El pipeline falló con una excepción no recuperable: {error_msg}")
    write_local_log(issue_id, title, False, f"Fallo Crítico: {error_msg}", run_log_dir)
    try:
        issue = runtime.repo.get_issue(number=issue_id)
        for lbl in ["status:in-progress", "ai:ready-to-code"]:
            if lbl in [l.name for l in issue.labels]: issue.remove_from_labels(lbl)
        try: runtime.repo.get_label("status:failed")
        except: runtime.repo.create_label("status:failed", "ff0000")
        issue.add_to_labels("status:failed")

        if flat_gates and design is not None and generated_files is not None and issue_description is not None:
            logging.info("Analizando el fallo del pipeline con el agente LLM...")
            try:
                report = agent_analyze_pipeline_failure(issue_id, title, issue_description, design or {}, generated_files or {}, flat_gates, runtime, error_msg=error_msg, pipeline_exc=pipeline_exc)
                with open(os.path.join(run_log_dir, "post_mortem_report.md"), "w", encoding="utf-8") as f:
                    f.write(report)
                issue.create_comment(f"## 🚨 SDLC Pipeline Post-Mortem\nEl Agente falló durante la ejecución: `{error_msg}`\n\n### Análisis Técnico:\n{report}\n\nRevisa los logs locales en `{run_log_dir}`.")
            except Exception as e:
                logging.error(f"Fallo al generar análisis LLM del pipeline: {e}")
                issue.create_comment(f"## Fallo SDLC Pipeline\nEl Agente fallo durante la ejecucion: `{error_msg}`\nRevisa los logs locales en `{run_log_dir}`.")
        else:
            issue.create_comment(f"## Fallo SDLC Pipeline\nEl Agente fallo durante la ejecucion: `{error_msg}`\nRevisa los logs locales en `{run_log_dir}`.")

    except Exception as gh_exc:
        logging.error(f"Fallo al actualizar el issue tras un error crítico: {gh_exc}")
    if pipeline_exc:
        raise pipeline_exc

def validate_issue_eligibility(issue_id: int, runtime: RuntimeClients) -> None:
    try:
        issue = runtime.repo.get_issue(number=issue_id)
    except Exception as e:
        raise PreflightError(f"No se pudo obtener el Issue #{issue_id}: {e}")

    labels = [l.name for l in issue.labels]
    if "ai:ready-to-code" not in labels:
        raise PreflightError(f"El Issue #{issue_id} no tiene la etiqueta 'ai:ready-to-code'.")

    # Check PO deployment metadata
    body = issue.body or ""
    import re
    parent_match = re.search(r"PO_PARENT_EPIC=(\d+)", body)
    index_match = re.search(r"PO_CHILD_INDEX=(\d+)", body)
    fingerprint_match = re.search(r"FINGERPRINT=([a-f0-9]{16})", body)
    if not parent_match or not index_match or not fingerprint_match:
        raise PreflightError(f"El Issue #{issue_id} no contiene metadata de PO (PO_PARENT_EPIC, PO_CHILD_INDEX, FINGERPRINT validos).")

    parent_epic_id = int(parent_match.group(1))
    try:
        parent_epic = runtime.repo.get_issue(number=parent_epic_id)
    except Exception:
        raise PreflightError(f"Parent Epic #{parent_epic_id} referenced by Issue #{issue_id} no existe.")

    parent_labels = [l.name for l in parent_epic.labels]
    if "gate:deployed" not in parent_labels:
        raise PreflightError(f"Parent Epic #{parent_epic_id} no tiene la etiqueta 'gate:deployed'.")

def transition_issue_status(issue_id: int, runtime: RuntimeClients) -> None:
    issue_to_update = runtime.repo.get_issue(number=issue_id)
    issue_to_update.remove_from_labels("ai:ready-to-code")
    try:
        runtime.repo.get_label("status:in-progress")
    except Exception:
        runtime.repo.create_label("status:in-progress", "fef2c0")
    issue_to_update.add_to_labels("status:in-progress")

def run_pipeline(issue_id: int, run_id: str, run_log_dir: str, runtime: RuntimeClients) -> None:
    context_manager = RepositoryContextManager()
    pipeline_passed = False
    title, desc = "", ""
    design: dict = {}
    generated_files: dict[str, str] = {}
    all_attempt_results: list[list[GateResult]] = []
    flat_gates: list[GateResult] = []
    try:
        validate_issue_eligibility(issue_id, runtime)
        transition_issue_status(issue_id, runtime)
        title, desc = fetch_issue(issue_id, runtime.repo)
        logging.info(f"Pipeline iniciado - Issue #{issue_id}: '{title}'")

        # --- PHASE 1: Contract Generation and Validation (Critical, Fail-Fast) ---
        initial_gates: list[GateResult] = []

        def _record(gate: GateResult) -> GateResult:
            initial_gates.append(gate)
            flat_gates.append(gate)
            return gate

        preflight_errors = base_preflight()
        _record(GateResult(attempt=1, name="base_preflight", executed=True, passed=not preflight_errors, output="\n".join(preflight_errors) or "Herramientas base disponibles."))
        if preflight_errors:
            error_str = " | ".join(preflight_errors)
            logging.error(f"Fallo en el preflight base: {preflight_errors}")
            raise PreflightError(error_str)

        context_budget = ContextBudget()
        repo_context = context_manager.build_repository_context(desc, context_budget)
        logging.info(f"Contexto del repositorio construido. {len(repo_context.source_index)} archivos fuente y {len(repo_context.test_index)} archivos de test indexados.")
        logging.info(f"Seleccionados {len(repo_context.relevant_source_files)} archivos fuente y {len(repo_context.relevant_test_files)} de test como contexto relevante.")
        if repo_context.architecture_conflicts:
            logging.warning(f"Se detectaron {len(repo_context.architecture_conflicts)} conflictos entre la arquitectura y el código real.")

        # --- PHASE 1b: Architecture + Contract Validation ---
        arch_consistency_passed = not any(c.blocks_execution for c in repo_context.architecture_conflicts)
        arch_consistency_output = json.dumps([c.model_dump() for c in repo_context.architecture_conflicts], indent=2) if repo_context.architecture_conflicts else "No se detectaron conflictos de arquitectura."
        _record(GateResult(attempt=1, name="architecture_consistency", executed=True, passed=arch_consistency_passed, output=arch_consistency_output))
        if not arch_consistency_passed:
            blocking_conflicts_str = json.dumps([c.model_dump() for c in repo_context.architecture_conflicts if c.blocks_execution], indent=2)
            logging.error(f"Conflictos de arquitectura bloqueantes detectados. El pipeline se detendrá. Conflictos: {blocking_conflicts_str}")
            raise ContractGenerationError("Conflictos de arquitectura bloqueantes detectados.")

        canonical_contract: AcceptanceContract
        from orchestrator_core.exceptions import (
            CandidateSchemaError, SemanticFidelityError, ContractConsistencyError,
            ContractPreflightError, EnvironmentPreflightError, ContractCapabilityError,
            ContractGenerationExhaustedError
        )


        attempt_contract = 1
        max_contract_attempts = 3
        diagnostics = []
        prior_contract_feedback = ""
        import collections
        Diagnostic = collections.namedtuple('Diagnostic', ['attempt', 'category', 'violation', 'final_phase'])
        while attempt_contract <= max_contract_attempts:
            try:
                canonical_contract = agent_generate_acceptance_contract(title, desc, repo_context, runtime, prior_feedback=prior_contract_feedback)
                logging.info(f"Contrato Canónico generado: {canonical_contract.model_dump_json(indent=2)}")
                _record(GateResult(attempt=attempt_contract, name="contract_generation", executed=True, passed=True, output="Contrato generado con éxito."))

                # Gate: Semantic fidelity FIRST (before consistency)
                try:
                    validate_semantic_fidelity(canonical_contract, title, desc, repo_context)
                except SemanticFidelityError as sf_e:
                    _record(GateResult(attempt=attempt_contract, name="contract_semantic_fidelity", executed=True, passed=False, output=str(sf_e)))
                    raise
                _record(GateResult(attempt=attempt_contract, name="contract_semantic_fidelity", executed=True, passed=True, output="Fidelidad semántica verificada."))

                consistent, consistency_errors = validate_contract_consistency(canonical_contract)
                _record(GateResult(attempt=attempt_contract, name="contract_consistency", executed=True, passed=consistent, output="\n".join(consistency_errors) if consistency_errors else "Contrato consistente."))
                if not consistent:
                    raise ContractConsistencyError(f"Contrato inconsistente: {consistency_errors}")

                try:
                    gate_plan = _derive_gate_plan(repo_context, canonical_contract)
                except PreflightError as gp_e:
                    # PreflightError from _derive_gate_plan is contract-caused -> retryable
                    raise ContractPreflightError(str(gp_e)) from gp_e

                policy_errors = validate_testing_policy_compatibility(gate_plan.test_framework, canonical_contract)
                if policy_errors:
                    raise ContractPreflightError(" | ".join(policy_errors))

                # Tool/environment preflight: non-retryable (environment failure)
                tool_errors = tool_preflight(gate_plan)
                _record(GateResult(attempt=attempt_contract, name="tool_preflight", executed=True, passed=not tool_errors, output="\n".join(tool_errors) if tool_errors else "Herramientas de análisis disponibles."))
                if tool_errors:
                    raise EnvironmentPreflightError(" | ".join(tool_errors))

                contract_capabilities_valid, contract_capabilities_errors = validate_contract_capabilities(canonical_contract, _validator_registry)
                _record(GateResult(attempt=attempt_contract, name="contract_capabilities_validation", executed=True, passed=contract_capabilities_valid, output="\n".join(contract_capabilities_errors)))
                if not contract_capabilities_valid:
                    raise ContractCapabilityError("Contrato generado con reglas no soportadas.")

                relevant_context_errors = validate_relevant_context_files(repo_context, canonical_contract)
                _record(GateResult(attempt=attempt_contract, name="relevant_context_validation", executed=True, passed=not relevant_context_errors, output="\n".join(relevant_context_errors) if relevant_context_errors else "Archivos de contexto relevantes validados."))
                if relevant_context_errors:
                    raise ContractConsistencyError(" | ".join(relevant_context_errors))

                break # Success!

            except EnvironmentPreflightError:
                # Tool/environment failure: non-retryable, propagate immediately
                logging.error(f"Fallo de entorno no recuperable (intento {attempt_contract}): herramientas no disponibles.")
                _record(GateResult(attempt=attempt_contract, name="contract_generation", executed=True, passed=False, output="EnvironmentPreflightError: herramientas no disponibles."))
                raise

            except (CandidateSchemaError, SemanticFidelityError, ContractConsistencyError, ContractCapabilityError, ContractPreflightError) as e:
                logging.error(f"Fallo en contrato (intento {attempt_contract}): {e}")

                # Assign category and final_phase
                if isinstance(e, CandidateSchemaError):
                    cat = "CandidateSchemaError"
                    final_phase = "schema"
                elif isinstance(e, SemanticFidelityError):
                    cat = "SemanticFidelityError"
                    final_phase = "semantic_fidelity"
                elif isinstance(e, ContractConsistencyError):
                    cat = "ContractConsistencyError"
                    final_phase = "consistency"
                elif isinstance(e, ContractCapabilityError):
                    cat = "ContractCapabilityError"
                    final_phase = "capability"
                else:  # ContractPreflightError
                    cat = "ContractPreflightError"
                    final_phase = "gate_plan"

                diagnostics.append(Diagnostic(attempt=attempt_contract, category=cat, violation=str(e), final_phase=final_phase))
                prior_contract_feedback = str(e)

                if attempt_contract >= max_contract_attempts:
                    raise ContractGenerationExhaustedError("Exhausted contract generation attempts", diagnostics=diagnostics) from e
                attempt_contract += 1
            except Exception as e:
                logging.error(f"Fallo crítico al generar el contrato de aceptación: {e}")
                _record(GateResult(attempt=attempt_contract, name="contract_generation", executed=True, passed=False, output=f'{type(e).__name__}: {str(e)}'))
                raise

        # Cargar el contenido de los relevant_context_files solicitados por contrato respetando ContextBudget
        _base_tokens = estimate_repository_context_tokens(repo_context, desc, canonical_contract)
        _remaining_budget = max(0, context_budget.maximum_input_tokens - context_budget.reserved_output_tokens - _base_tokens)

        for f in canonical_contract.relevant_context_files:
            if f in repo_context.relevant_source_files or f in repo_context.relevant_test_files:
                continue # Ya cargado
            try:
                safe_path = resolve_safe_path(".", f)
                with open(safe_path, "r", encoding="utf-8") as f_obj:
                    content = f_obj.read()
                    tok_estimate = len(content) // 4
                    if tok_estimate <= _remaining_budget:
                        if f in repo_context.test_index:
                            repo_context.relevant_test_files[f] = content
                        else:
                            repo_context.relevant_source_files[f] = content
                        _remaining_budget -= tok_estimate
                        logging.info(f"Cargado contexto adicional por contrato: {f} ({tok_estimate} tokens)")
                    else:
                        logging.warning(f"Omitido contexto adicional (fuera de presupuesto): {f}")
            except Exception as e:
                logging.warning(f"No se pudo cargar contexto '{f}': {e}")


        # --- PHASE 2: Iterative Development Attempts ---

        class ContextUsage:
            def __init__(self, token_limit: int):
                self.token_limit = token_limit
                self.current_tokens = 0
            def can_add(self, tokens: int) -> bool:
                return (self.current_tokens + tokens) <= self.token_limit
            def add(self, tokens: int):
                self.current_tokens += tokens

        def locate_symbol(symbol: str, context: RepositoryContext) -> list[str]:
            found = []
            for path, summary in context.source_index.items():
                if symbol in summary.classes or symbol in summary.functions or symbol in summary.signatures:
                    found.append(path)
            for path, summary in context.test_index.items():
                if symbol in summary.classes or symbol in summary.functions or symbol in summary.signatures:
                    found.append(path)
            return found

        # Compute tokens already consumed by the base context payloads
        initial_tokens = estimate_repository_context_tokens(repo_context, desc, canonical_contract)
        # Reuse the context_budget created for build_repository_context
        max_tokens = context_budget.maximum_input_tokens
        reserved = context_budget.reserved_output_tokens
        remaining_tokens = max(0, max_tokens - reserved - initial_tokens)
        context_usage = ContextUsage(remaining_tokens)

        attempt, max_attempts, pipeline_passed = 1, 3, False
        context_expansion_count = 0
        max_context_expansions = 2
        requested_context_history: set[str] = set()

        generated_files, feedback_dict = {}, {}
        design, design_feedback = None, ""
        all_attempt_results.append(initial_gates) # Add initial gates to results


        while attempt <= max_attempts and not pipeline_passed:
            current_attempt_gates: list[GateResult] = []

            # --- AISLAMIENTO DE INTENTOS: Restaurar el workspace a un estado limpio ---
            logging.info(f"Preparando intento {attempt}/{max_attempts}. Restaurando workspace a estado base...")
            subprocess.run(["git", "reset", "--hard"], check=True, capture_output=True, timeout=120)
            subprocess.run(["git", "clean", "-fd"], check=True, capture_output=True, timeout=120)

            logging.info(f"Ejecutando ciclo de desarrollo (Intento {attempt}/{max_attempts})...")

            if design is None: # Diseñar solo si no existe un plan previo
                logging.info("Diseñando plan estructural base o rediseñando tras rechazo...")
                design = agent_analyze_and_design(
                    title,
                    desc,
                    canonical_contract,
                    repo_context,
                    runtime,
                    context_manager=context_manager,
                    design_feedback=design_feedback
                )

                if design and design.get("is_context_request"):
                    if context_expansion_count >= max_context_expansions:
                        current_attempt_gates.append(GateResult(attempt=attempt, name="context_expansion", executed=True, passed=False, output="Límite de expansiones alcanzado."))
                        all_attempt_results.append(current_attempt_gates)
                        design = None  # Reset so next attempt calls architect fresh, not this stale context-request design
                        attempt += 1
                        continue

                    context_req = design.get("context_request", {})
                    reason = context_req.get("reason", "Sin razón provista")
                    logging.info(f"[Arquitecto pide más contexto]: {reason}")

                    requested_paths = set(context_req.get("requested_files", []))

                    # Symbol resolution
                    for sym in context_req.get("requested_symbols", []):
                        requested_paths.update(locate_symbol(sym, repo_context))

                    added_files = 0
                    for f in requested_paths:
                        if f in requested_context_history:
                            continue # Already evaluated this file

                        requested_context_history.add(f)

                        if f in repo_context.source_index or f in repo_context.test_index:
                            if f not in repo_context.relevant_source_files and f not in repo_context.relevant_test_files:
                                # Estimate token usage. fallback if not present
                                summary = repo_context.source_index.get(f) or repo_context.test_index.get(f)
                                tokens = getattr(summary, 'estimated_tokens', 1000)

                                if not context_usage.can_add(tokens):
                                    logging.warning(f"No se puede inyectar '{f}', supera el presupuesto de tokens.")
                                    continue

                                content = context_manager.get_file_content(f)
                                if f in repo_context.test_index:
                                    repo_context.relevant_test_files[f] = content
                                else:
                                    repo_context.relevant_source_files[f] = content

                                context_usage.add(tokens)
                                added_files += 1

                    context_expansion_count += 1
                    if added_files > 0:
                        design_feedback = f"Se han inyectado {added_files} archivos solicitados en tu contexto. Procede con el diseño."
                    else:
                        design_feedback = "Los archivos solicitados no existen, ya están en tu contexto, o exceden el límite de tokens. Procede con el diseño."

                    design = None
                    continue

                design_feedback = "" # Consume feedback

            if design is None: # If agent_analyze_and_design failed to produce a valid design
                logging.error("El agente de diseño no pudo generar un plan válido.")
                current_attempt_gates.append(GateResult(attempt=attempt, name="design_generation", executed=True, passed=False, output="El agente de diseño no pudo generar un plan válido."))
                all_attempt_results.append(current_attempt_gates)
                attempt += 1
                continue

            logging.info(f"Justificacion del Arquitecto:\n{design.get('architecture_justification', 'N/A')}")

            # GATE: Validación del diseño
            design_valid, design_errors = validate_design(design, canonical_contract)
            current_attempt_gates.append(GateResult(attempt=attempt, name="design_validation", executed=True, passed=design_valid, output="\n".join(design_errors)))
            if not design_valid:
                logging.warning(f"El diseño fue rechazado por el validador de planes: {design_errors}")
                design_feedback = "\n".join(design_errors)
                design = None # Forzar rediseño
                all_attempt_results.append(current_attempt_gates)
                attempt += 1
                continue

            # D5-B: Materialize valid generated files from cache ONLY AFTER successful design validation against the clean baseline
            materialize_cached_files(generated_files, feedback_dict, context_manager)

            code_actions = [a for a in design.get('actions', []) if a['operation'].upper() in ["CREATE", "MODIFY"] and a['file_type'] != 'test']
            test_actions = [a for a in design.get('actions', []) if a['operation'].upper() in ["CREATE", "MODIFY"] and a['file_type'] == 'test' and not a['filepath'].endswith("__init__.py")]

            for act in [a for a in design.get('actions', []) if a['operation'].upper() == "DELETE"]:
                safe_path = resolve_safe_path(".", act['filepath'])
                if os.path.exists(safe_path):
                    os.remove(safe_path)

            # --- BUCLE DE IMPLEMENTACIÓN Y VALIDACIÓN TEMPRANA ---
            generation_failed = False
            for act in code_actions + test_actions:
                path = act['filepath']
                global_feedback = feedback_dict.get("all", "")
                file_feedback = feedback_dict.get(path, "")

                if path in generated_files and not file_feedback and not global_feedback:
                    continue

                current_feedback = f"{global_feedback}\n{file_feedback}".strip()

                if act in code_actions:
                    file_contract = _create_file_contract(path, canonical_contract)
                    code = agent_implement_code(
                        act,
                        file_contract,
                        design,
                        generated_files,
                        repo_context,
                        runtime,
                        context_manager=context_manager,
                        feedback=current_feedback
                    )
                else:
                    file_contract = _create_file_contract(path, canonical_contract)
                    code = agent_generate_tests(
                        act,
                        file_contract,
                        generated_files,
                        desc,
                        repo_context,
                        gate_plan.test_framework,
                        runtime,
                        context_manager=context_manager,
                        feedback=current_feedback
                    )

                # GATES: Calidad de código y AST contractual
                is_valid, quality_report = validate_code_quality(code, path, repo_context.quality_policy)
                contract_errors = validate_contractual_ast(code, path, canonical_contract, repo_context=repo_context)

                if not is_valid:
                    logging.warning(f"El código para '{path}' fue rechazado por calidad básica: {quality_report}")
                    current_attempt_gates.append(GateResult(attempt=attempt, name=f"generation_quality_{path}", executed=True, passed=False, output=quality_report))
                    feedback_dict[path] = quality_report
                    generation_failed = True
                    break
                if contract_errors:
                    logging.warning(f"El código para '{path}' fue rechazado por validación contractual AST: {contract_errors}")
                    error_str = "\n".join(contract_errors)
                    current_attempt_gates.append(GateResult(attempt=attempt, name=f"generation_ast_{path}", executed=True, passed=False, output=error_str))
                    feedback_dict[path] = "\n".join(contract_errors)
                    generation_failed = True
                    break

                generated_files[path] = code
                safe_path = resolve_safe_path(".", path)
                dir_name = os.path.dirname(safe_path)
                if dir_name: os.makedirs(dir_name, exist_ok=True)
                with open(safe_path, "w", encoding="utf-8") as f: f.write(code)

                # Limpiar feedback una vez usado
                feedback_dict.pop(path, None)

            if generation_failed:
                logging.warning("Fallo en la generación o validación AST. Reintentando...")
                all_attempt_results.append(current_attempt_gates)
                attempt += 1
                continue

            # Limpiar feedback global si se usó
            feedback_dict.pop("all", None)

            # GATE: Validación de manifiesto
            manifest_valid, manifest_error = validate_generated_manifest(generated_files, canonical_contract, repo_context)
            current_attempt_gates.append(GateResult(attempt=attempt, name="manifest_validation", executed=True, passed=manifest_valid, output=manifest_error))
            if not manifest_valid:
                logging.warning(f"Manifiesto de archivos generados incompleto: {manifest_error}")
                feedback_dict["all"] = f"Faltan archivos en la generación: {manifest_error}"
                all_attempt_results.append(current_attempt_gates)
                attempt += 1
                continue

            # GATE: Validación del estado final del sistema de archivos
            final_state_valid, final_state_error = validate_final_state(canonical_contract)
            current_attempt_gates.append(GateResult(attempt=attempt, name="final_state_validation", executed=True, passed=final_state_valid, output=final_state_error))
            if not final_state_valid:
                logging.warning(f"El estado final del sistema de archivos no cumple el contrato: {final_state_error}")
                feedback_dict["all"] = f"El estado final del sistema de archivos es incorrecto: {final_state_error}"
                all_attempt_results.append(current_attempt_gates)
                attempt += 1
                continue

            if gate_plan.run_mypy:
                if repo_context.structured_config.mypy_targets:
                    mypy_passed, mypy_log = run_mypy([], repo_context.quality_policy)
                    current_attempt_gates.append(GateResult(attempt=attempt, name="mypy", executed=True, passed=mypy_passed, output=mypy_log))
                    if not mypy_passed:
                        logging.warning(f"MyPy encontró errores:\n{mypy_log}")
                        feedback_dict = parse_compiler_output(mypy_log)
                        all_attempt_results.append(current_attempt_gates)
                        attempt += 1
                        continue
                else:
                    files_for_mypy = build_mypy_scope(generated_files, repo_context)

                    if not files_for_mypy:
                        current_attempt_gates.append(GateResult(attempt=attempt, name="mypy", executed=False, passed=True, output="Sin archivos válidos para MyPy."))
                    else:
                        mypy_passed, mypy_log = run_mypy(files_for_mypy, repo_context.quality_policy)
                        current_attempt_gates.append(GateResult(attempt=attempt, name="mypy", executed=True, passed=mypy_passed, output=mypy_log))
                        if not mypy_passed:
                            logging.warning(f"MyPy encontró errores:\n{mypy_log}")
                            feedback_dict = parse_compiler_output(mypy_log)
                            all_attempt_results.append(current_attempt_gates)
                            attempt += 1
                            continue

            else:
                current_attempt_gates.append(GateResult(attempt=attempt, name="mypy", executed=False, passed=True, output="MyPy deshabilitado por el plan de gates."))

            # GATE: Unit Tests
            if gate_plan.run_tests:
                test_passed, test_log = True, ""
                for act in test_actions:
                    path = act['filepath']
                    success, log = run_local_tests(resolve_safe_path(".", path), framework=gate_plan.test_framework)
                    test_log += f"\n--- {path} ---\n{log}"
                    if not success:
                        test_passed = False
                        feedback_dict[path] = log

                if test_passed:
                    if not repo_context.test_index and not canonical_contract.protected_tests:
                        # D5-A: Greenfield regression semantics
                        logging.info("Regresión baseline omitida: el repositorio inicial no contiene tests.")
                        regression_log = "Regresión baseline omitida: el repositorio inicial no contiene tests.\n"
                        test_log += f"\n--- REGRESIÓN COMPLETA ---\n{regression_log}"
                    else:
                        logging.info(f"Ejecutando suite de regresión completa de {gate_plan.test_framework}...")
                        if gate_plan.test_framework == "unittest":
                            regression_result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-v"], capture_output=True, text=True, timeout=600)
                        else:
                            regression_result = subprocess.run([sys.executable, "-m", "pytest", "-v"], capture_output=True, text=True, timeout=600)

                        test_passed = regression_result.returncode == 0
                        regression_log = regression_result.stdout + regression_result.stderr

                        # D5-A: Fail closed if baseline tests were expected but unittest ran 0 tests
                        if gate_plan.test_framework == "unittest" and "Ran 0 tests" in regression_log:
                            test_passed = False

                        test_log += f"\n--- REGRESIÓN COMPLETA ---\n{regression_log}"

                current_attempt_gates.append(GateResult(attempt=attempt, name="tests", executed=True, passed=test_passed, output=test_log))
                if not test_passed:
                    logging.warning(f"Pruebas unitarias fallaron. Realimentando sistema...\n{test_log}")
                    all_attempt_results.append(current_attempt_gates)
                    attempt += 1
                    continue
            else:
                current_attempt_gates.append(GateResult(attempt=attempt, name="tests", executed=False, passed=True, output="Tests deshabilitados por el plan de gates."))

            # GATE: Ruff/Vulture
            if gate_plan.run_ruff or gate_plan.run_vulture:
                combined_test_paths = set(repo_context.test_index.keys()) | {act["filepath"] for act in test_actions}
                static_passed, static_log = run_static_analysis(list(generated_files.keys()), gate_plan, combined_test_paths)
                reload_code_after_ruff(generated_files, context_manager) # Recargar por si --fix modificó algo

                # Re-evaluar AST y política de calidad por si Ruff rompió algo
                contract_failed = False
                for p, c in generated_files.items():
                    c_errors = validate_contractual_ast(c, p, canonical_contract, repo_context=repo_context)
                    q_valid, q_errors = validate_code_quality(c, p, repo_context.quality_policy)

                    if c_errors or not q_valid:
                        logging.warning(f"Ruff --fix introdujo regresiones en '{p}'")
                        err_msg = ""
                        if c_errors: err_msg += "\nErrores de contrato:\n" + "\n".join(c_errors)
                        if not q_valid:
                            errors_str = q_errors if isinstance(q_errors, str) else "\n".join(q_errors)
                            err_msg += "\nErrores de calidad estricta:\n" + errors_str

                        feedback_dict[p] = err_msg
                        contract_failed = True
                        static_passed = False
                        static_log += f"\n[Ruff --fix Regression] {p}: {err_msg}"

                # Verify that Ruff didn't revert a file to its baseline state, effectively erasing the modification
                manifest_valid, manifest_error = validate_generated_manifest(generated_files, canonical_contract, repo_context)
                if not manifest_valid:
                    logging.warning(f"Ruff --fix introdujo regresiones en el manifiesto: {manifest_error}")
                    contract_failed = True
                    static_passed = False
                    static_log += f"\n[Ruff --fix Regression Manifest]: {manifest_error}"

                current_attempt_gates.append(GateResult(attempt=attempt, name="static_analysis", executed=True, passed=static_passed, output=static_log))
                if not static_passed:
                    logging.warning(f"Análisis estático falló:\n{static_log}")
                    if not contract_failed:
                        feedback_dict = {"all": static_log}
                    all_attempt_results.append(current_attempt_gates)
                    attempt += 1
                    continue
            else:
                current_attempt_gates.append(GateResult(attempt=attempt, name="static_analysis", executed=False, passed=True, output="Análisis estático (Ruff/Vulture) deshabilitado por el plan de gates."))

            # GATE: Code Reviewer
            review_result = agent_code_reviewer(design, generated_files, desc, canonical_contract, repo_context, runtime)
            current_attempt_gates.append(GateResult(attempt=attempt, name="code_reviewer", executed=True, passed=review_result.approved, output=json.dumps(review_result.model_dump(), indent=2)))
            if not review_result.approved:
                logging.warning(f"Rechazo del Code Reviewer: {review_result.findings}")
                if review_result.design_conflict:
                    design_feedback = "\n".join(
                        finding.message for finding in review_result.findings
                    )
                    design = None # Forzar rediseño
                    generated_files.clear()
                    feedback_dict.clear()
                else:
                    feedback_dict = {f.filepath: f.message for f in review_result.findings}
                all_attempt_results.append(current_attempt_gates)
                attempt += 1
                continue

            # GATE: Auditoría final de seguridad y arquitectura
            audit_result = agent_security_audit(design, generated_files, canonical_contract, runtime, repo_context)
            audit_report = "\n".join(audit_result.findings) if audit_result.findings else "Aprobado"
            current_attempt_gates.append(GateResult(attempt=attempt, name="security_audit", executed=True, passed=audit_result.approved, output=audit_report))
            if not audit_result.approved:
                logging.warning(f"Rechazo de Robustez Estructural (SAST): {audit_report}")
                feedback_dict = {"all": audit_report}
                all_attempt_results.append(current_attempt_gates)
                attempt += 1
                continue

            logging.info("Todos los Quality Gates pasados.")
            pipeline_passed = True
            all_attempt_results.append(current_attempt_gates)

        if not pipeline_passed:
            error_msg = f"El pipeline colapsó tras {max_attempts} reintentos."
            logging.error(error_msg)

            pm_report = agent_analyze_pipeline_failure(issue_id, title, desc, design or {}, generated_files, [g for attempt_gates in all_attempt_results for g in attempt_gates], runtime)

            # Save post-mortem report to its own file in the persistent log dir
            pm_report_path = os.path.join(run_log_dir, "post_mortem_report.md")
            with open(pm_report_path, "w", encoding="utf-8") as f:
                f.write(pm_report)
            logging.info(f"Post-mortem report saved to {pm_report_path}")

            # --- LOGICA DE DELEGACION AUTOMATIZADA AL PO AGENT ---
            if "[ACTION: DELEGATE_TO_PO]" in pm_report:
                logging.warning("El post-mortem requiere validacion humana del PO. Ejecucion detenida.")
                try:
                    issue = runtime.repo.get_issue(number=issue_id)
                    if "status:in-progress" in [l.name for l in issue.labels]:
                        issue.remove_from_labels("status:in-progress")
                    try:
                        runtime.repo.get_label("po:human-validation-required")
                    except:
                        runtime.repo.create_label("po:human-validation-required", "fbca04")
                    issue.add_to_labels("po:human-validation-required")
                    issue.create_comment("## Fallo SDLC Pipeline\nEl Agente Orquestador ha detectado problemas funcionales o estructurales en el Issue que requieren validación de Product Owner humano. Revisa el reporte Post-Mortem en los logs locales de la ejecución.")
                except Exception as e:
                    logging.error(f"Fallo al actualizar etiquetas para validacion humana: {e}")
                return
            else:
                try:
                    issue = runtime.repo.get_issue(number=issue_id)
                    if "status:in-progress" in [l.name for l in issue.labels]:
                        issue.remove_from_labels("status:in-progress")
                    try:
                        runtime.repo.get_label("status:failed")
                    except Exception:
                        runtime.repo.create_label("status:failed", "d93f0b") # Red
                    issue.add_to_labels("status:failed")
                    issue.create_comment("Pipeline execution failed due to technical errors. See orchestrator logs for the Post-Mortem report.")
                except Exception as e:
                    logging.error(f"Could not update GitHub issue status to 'failed': {e}")
                write_local_log(issue_id, title, False, error_msg, run_log_dir)
            return

        final_gates = all_attempt_results[-1]

        # Stage all changes to get a clean diff for documentation
        # This includes new files, modifications, and deletions that have been processed.
        subprocess.run(["git", "add", "-A"], check=True, timeout=60)
        _sanitize_staging_area()
        diff_result = subprocess.run(["git", "diff", "--staged"], capture_output=True, text=True, timeout=120)
        git_diff = diff_result.stdout

        report = agent_generate_execution_report(design, generated_files, "\n".join([g.output for g in final_gates if g.name=='tests']), "\n".join([g.output for g in final_gates if g.name=='security_audit']), issue_id, title, runtime)
        arch = agent_update_architecture_doc(
            issue_id,
            title,
            desc,
            design,
            generated_files,
            repo_context.architecture_document,
            final_gates,
            git_diff,
            runtime,
        )
        man = agent_update_user_manual(issue_id, title, desc, design, generated_files, runtime)

        try:
            # The deploy function will commit the staged changes
            deploy_to_github(design, generated_files, report, arch, man, issue_id, run_id, runtime)
            write_local_log(issue_id, title, True, "Despliegue y PR completado.", run_log_dir)
        except Exception as e:
            write_local_log(issue_id, title, False, f"Fallo Git al desplegar: {e}", run_log_dir)
            raise
    except Exception as pipeline_exc:
        # Flatten any nested gate lists and pass flat_gates which already includes initial_gates
        handle_pipeline_failure(issue_id, title, str(pipeline_exc), run_log_dir, runtime, pipeline_exc, gate_results=flat_gates, design=design, generated_files=generated_files, issue_description=desc)

def normalize_remote(remote_url: str) -> str:
    match = re.search(r'(?:github\.com[:/])(.*?)(?:\.git)?$', remote_url)
    return match.group(1) if match else remote_url

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Framework de Agentes Autonomos SDLC")
    parser.add_argument("--issue", type=int, required=True, help="Numero del Issue a procesar")
    parser.add_argument("--target-repo", type=str, help="GitHub repo (ej. Oxcalibur/bookai-engine)")
    parser.add_argument("--target-workspace", type=str, help="Ruta local absoluta al target")
    parser.add_argument("--target-branch", type=str, default="main", help="Base branch del target")
    args = parser.parse_args()

    original_cwd = os.getcwd()
    run_id = f"RUN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Define persistent log directory outside the worktree
    run_log_dir = os.path.join(original_cwd, ".agent-runs", run_id)
    os.makedirs(run_log_dir, exist_ok=True)

    worktree_dir = os.path.join(original_cwd, ".agent-worktrees", run_id)
    worktree_created = False

    try:
        # 1. O1: VALIDATE TARGET ISOLATION
        if bool(args.target_repo) != bool(args.target_workspace):
            print("Error: Se deben proveer ambos o ninguno (--target-repo y --target-workspace)")
            sys.exit(1)

        if args.target_repo and args.target_workspace:
            if not os.path.isdir(args.target_workspace):
                print(f"Error: Target workspace no existe: {args.target_workspace}")
                sys.exit(1)
            target_info = {}
            try:
                root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=args.target_workspace, text=True, stderr=subprocess.DEVNULL).strip()
                origin = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=args.target_workspace, text=True, stderr=subprocess.DEVNULL).strip()
                head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=args.target_workspace, text=True, stderr=subprocess.DEVNULL).strip()
                branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=args.target_workspace, text=True, stderr=subprocess.DEVNULL).strip()
                target_info = {"root": os.path.normpath(root), "origin": origin, "head": head, "branch": branch}
            except Exception:
                print(f"Error: Target workspace no es un repositorio Git: {args.target_workspace}")
                sys.exit(1)

            target_origin = normalize_remote(target_info["origin"])
            if target_origin != args.target_repo:
                print(f"Error: Target origin mismatch. Esperado: {args.target_repo}, Actual: {target_origin}")
                sys.exit(1)

            if target_info["branch"] != args.target_branch:
                print(f"Error: Target branch '{target_info['branch']}' no coincide con el base declarado '{args.target_branch}'.")
                sys.exit(1)

            try:
                status = subprocess.check_output(["git", "status", "--porcelain"], cwd=args.target_workspace, text=True, stderr=subprocess.PIPE).strip()
                if status:
                    print(f"Error: Target workspace '{args.target_workspace}' no está limpio (tiene archivos modificados o untracked).")
                    sys.exit(1)
            except Exception:
                print(f"Error verificando estado git en Target '{args.target_workspace}'.")
                sys.exit(1)

            # 2. O2/Platform-Side Credentials: Build runtime and check eligibility BEFORE worktree creation
            runtime = build_runtime_clients(target_repo=getattr(args, 'target_repo', None))
            validate_issue_eligibility(args.issue, runtime)

            # 3. Prepare isolated worktree linked to TARGET workspace
            branch_name = f"agent/issue-{args.issue}/{run_id}"
            logging.info(f"Creando worktree aislado en '{worktree_dir}' en la rama '{branch_name}' vinculado al TARGET {args.target_workspace}")
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, worktree_dir, target_info["head"]],
                cwd=args.target_workspace, check=True, capture_output=True, text=True, timeout=120
            )
            worktree_created = True
        else:
            # Fallback for existing tests that don't pass --target-repo (backward compatibility)
            ensure_git_setup()

            # Build runtime and check eligibility in platform context
            runtime = build_runtime_clients(target_repo=None)
            validate_issue_eligibility(args.issue, runtime)

            branch_name = f"agent/issue-{args.issue}/{run_id}"
            logging.info(f"Creando worktree aislado en '{worktree_dir}' en la rama '{branch_name}' vinculado a platform origin/main")
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, worktree_dir, "origin/main"],
                check=True, capture_output=True, text=True, timeout=120
            )
            worktree_created = True

        os.chdir(worktree_dir)

        # 4. Run pipeline inside the worktree
        run_pipeline(args.issue, run_id, run_log_dir, runtime)

    except ContractGenerationError as e:
        logging.error(f"Fallo en la fase de generación o validación del contrato: {e}")
        # The pipeline already logged the error, just ensure it exits gracefully.
    except subprocess.CalledProcessError as e:
        logging.error(f"Fallo en la operación de Git worktree: {e.stderr}")
    except Exception as e:
        logging.exception(f"Ocurrió un error inesperado en el pipeline: {e}")
    finally:
        os.chdir(original_cwd)
        if worktree_created and os.path.exists(worktree_dir):
            logging.info(f"Eliminando worktree: {worktree_dir}")
            cwd = args.target_workspace if getattr(args, 'target_repo', None) and getattr(args, 'target_workspace', None) else original_cwd
            subprocess.run(["git", "worktree", "remove", worktree_dir, "--force"], cwd=cwd, capture_output=True, text=True, timeout=120)
            subprocess.run(["git", "worktree", "prune"], cwd=cwd, capture_output=True, text=True, timeout=120)
