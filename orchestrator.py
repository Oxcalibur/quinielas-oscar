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
from pydantic import BaseModel, Field, ValidationError
from typing import Literal, Any

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

def write_local_log(issue_id, title, success, details="", run_log_dir="."):
    log_file = os.path.join(run_log_dir, "pipeline.log")
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] Issue #{issue_id} - '{title}' | Estado: {status}\n")
        if details: f.write(f"Detalle: {details}\n")
        f.write("-" * 80 + "\n")
    logging.info(f"Historial guardado en '{log_file}'")

def write_transactional_metadata(run_id, issue_id, title, success, design, commit_hash="N/A"):
    registry_file = "docs/metadata/runs_registry.json"
    os.makedirs("docs/metadata", exist_ok=True)
    registry = {}
    if os.path.exists(registry_file):
        try:
            with open(registry_file, "r", encoding="utf-8") as f: registry = json.load(f)
        except Exception: registry = {}
    created_files, modified_files, deleted_files = [], [], []
    for action in design.get("actions", []):
        filepath = action.get("filepath")
        op = action.get("operation", "").upper()
        if op == "CREATE": created_files.append(filepath)
        elif op == "MODIFY": modified_files.append(filepath)
        elif op == "DELETE": deleted_files.append(filepath)
            
    registry[run_id] = {
        "issue_id": issue_id, "title": title,
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "SUCCESS" if success else "FAILED",
        "commit_hash": commit_hash,
        "impact": {"created": created_files, "modified": modified_files, "deleted": deleted_files}
    }
    try:
        with open(registry_file, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=4, ensure_ascii=False)
            logging.info(f"Registro transaccional guardado en '{registry_file}'")
    except Exception as e:
            logging.warning(f"No se pudo actualizar el JSON de trazabilidad: {e}")

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
def fetch_issue(issue_id: int, repo) -> tuple[str, str]:
    logging.info(f"Leyendo requisitos en el Issue #{issue_id}...")
    issue = repo.get_issue(number=issue_id)
    return issue.title, issue.body



from orchestrator_core.context_budget import (
    estimate_repository_context_tokens,
)

from orchestrator_core.prompt_context import PromptContextBuilder







def summarize_dependency_file(filename: str, content: str) -> dict:
    import re
    if "poetry.lock" in filename or "Pipfile.lock" in filename:
        # Extract basic package names without all details to save tokens
        packages = re.findall(r'\[\[package\]\]\s+name\s*=\s*"([^"]+)"\s+version\s*=\s*"([^"]+)"', content)
        if not packages:
            packages = re.findall(r'name\s*=\s*"([^"]+)"', content) # fallback
        return {"type": "lockfile", "packages": packages[:100]} # limit to 100
    elif "requirements" in filename and filename.endswith(".txt"):
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('#')]
        return {"type": "requirements", "lines": lines[:100]}
    else:
        return {"type": "unknown", "content": content if len(content) // 4 < 1000 else content[:4000] + "\n...[TRUNCATED]"}

def agent_security_audit(
    design: dict, generated_files: dict[str, str], contract: AcceptanceContract, runtime: RuntimeClients, repo_context: RepositoryContext
) -> SecurityAuditResult:
    logging.info(f"Realizando auditoria de robustez del ecosistema modular con {MODEL_HEAVY}...")
    all_findings = []

    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)
    
    # 1. Base mandatory tokens (policy + contract)
    policy_str = repo_context.quality_policy.model_dump_json(indent=2)
    contract_str = contract.model_dump_json(indent=2)
    
    # 2. Config & Dependencies (new additions to context)
    config_str = repo_context.structured_config.model_dump_json(indent=2)
    deps_str = json.dumps(repo_context.structured_config.dependencies + repo_context.structured_config.dev_dependencies, indent=2)
    
    # 3. Coherence Graph (summary of existing state + generated files)
    coherence_graph = build_coherence_summary(generated_files, repo_context)
    graph_str = json.dumps(coherence_graph, indent=2)

    design_compact = json.dumps(design, separators=(',', ':')) if design else "{}"
    dependency_evidence = {}
    for filename, content in repo_context.dependency_files.items():
        dependency_evidence[filename] = summarize_dependency_file(filename, content)
    dep_json = json.dumps(dependency_evidence, indent=2)
    
    # Calculate required base budget
    req_base_str = f"""
        - Politica de calidad activa: {policy_str}
        - Contrato Canonico (Reglas de Arquitectura): {contract_str}
        - Configuracion Estructurada Completa: {config_str}
        - Dependencias (Prod/Dev): {deps_str}
        - Diseño Arquitectónico:
        {design_compact}

        Evidencia de Dependencias:
        {dep_json}

        Grafo de Coherencia: {graph_str}
    """
    req_base_tokens = len(req_base_str) // 4
    
    if not budget.can_add(req_base_tokens):
        logging.warning("El contexto base excede el presupuesto. Fallando rapido.")
        return SecurityAuditResult(
            approved=False, 
            findings=["El contexto base del Security Audit excede el limite de tokens."]
        )
    budget.add(req_base_tokens)

    # 4. Optional context (Architecture and Conflicts)
    arch_doc = repo_context.architecture_document or "[No hay documento de arquitectura]"
    arch_tok = len(arch_doc) // 4
    if arch_tok > 8000:
        arch_doc = arch_doc[:8000 * 4] + "\n... [TRUNCADO]"
        arch_tok = len(arch_doc) // 4
        
    if budget.can_add(arch_tok):
        budget.add(arch_tok)
    else:
        arch_doc = "[Omitido por presupuesto]"

    conflicts = json.dumps([c.model_dump() for c in repo_context.architecture_conflicts], indent=2)
    conf_tok = len(conflicts) // 4
    if budget.can_add(conf_tok):
        budget.add(conf_tok)
    else:
        conflicts = "[Omitido por presupuesto]"

    base_prompt = f"""
        Contexto Adicional para Auditoria:
        - Politica de calidad activa: {policy_str}
        - Contrato Canonico (Reglas de Arquitectura): {contract_str}
        - Configuracion Estructurada Completa: {config_str}
        - Dependencias (Prod/Dev): {deps_str}
        - Diseño Arquitectónico:
        {design_compact}
        - Evidencia de Dependencias:
        {dep_json}
        - Documento de Arquitectura Base: {arch_doc}
        - Conflictos de Arquitectura Detectados Previos: {conflicts}
        - Grafo de Coherencia de Imports: {graph_str}
    """

    available_chunk_tokens = budget.remaining - 2000 # leave buffer for fixed prompt wrapper
    if available_chunk_tokens <= 0:
        return SecurityAuditResult(approved=False, findings=["Sin presupuesto para procesar lotes de auditoria."])

    try:
        payloads = PromptContextBuilder.build_for_audit(generated_files, max_tokens=available_chunk_tokens)
    except PreflightError as e:
        return SecurityAuditResult(approved=False, findings=[str(e)])
    except Exception as e:
        return SecurityAuditResult(approved=False, findings=[f"Fallo al construir chunks de auditoria: {e}"])
        
    for i, payload in enumerate(payloads):
        prompt = base_prompt + f"""
        Archivos Generados (Lote {i+1} de {len(payloads)}):
        {payload.content}

        Actuas como un experto auditor de seguridad y arquitectura. Identifica SI O SI cualquier:
        1. Regresion de Robustez (ej: inyecciones de codigo, rutas inseguras, variables globales mutables).
        2. Dependencias externas o APIs sin envoltorios seguros ni validacion.
        3. Excepciones capturadas de manera generica ('except Exception:') sin logging contextual o relanzamiento.
        4. Falta de validacion de aserciones en los tests (tests que pasan solo con assert True).
        
        Responde exclusivamente con el JSON esperado.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SecurityAuditResult,
            temperature=0.0
        )
        try:
            ensure_prompt_fits(prompt, budget, "Security Audit Chunk")
            response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
            cleaned_json = extract_code(response.text, "json")
            result = SecurityAuditResult.model_validate_json(cleaned_json)
            if not result.approved:
                all_findings.extend(result.findings)
        except Exception as e:
            logging.error(f"Error parseando resultado de auditoria de seguridad: {e}")
            all_findings.append(f"Error parseando resultado de auditoria: {e}")

    return SecurityAuditResult(approved=len(all_findings)==0, findings=all_findings)

def agent_generate_execution_report(design: dict, generated_files: dict[str, str], pytest_log: str, sast_report: str, issue_id: int, title: str, runtime: RuntimeClients) -> str:
    logging.info(f"Compilando reporte de ejecucion para Issue #{issue_id}...")
    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=4000)

    # 4. MANDATORY
    architecture_justification = design.get("architecture_justification", "[no disponible]")
    manifest_str = str(list(generated_files.keys()))
    fixed_instructions = "Actúas como un ingeniero de release. Genera un reporte Markdown detallado del ciclo de ejecución. Incluye el título, la justificación de la arquitectura, resumen de dependencias/archivos modificados, resumen de calidad estática, y análisis de fallos en tests si los hay."

    # 6. SINGLE SOURCE OF TRUTH
    def build_final_prompt(content_text: str, failures_text: str, traceback_text: str, sast_text: str, tail_text: str) -> str:
        return f"""
    {fixed_instructions}
    
    Title/Issue: {title}
    Architecture Justification: {architecture_justification}
    Generated Files Manifest: {manifest_str}
    
    Content of generated files:
    {content_text}
    
    Test Failures/Errors:
    {failures_text}
    
    Relevant Tracebacks:
    {traceback_text}
    
    SAST:
    {sast_text}
    
    Test Tail Logs:
    {tail_text}
    """

    # 7. RESERVAR MANDATORY PRIMERO
    mandatory_prompt = build_final_prompt(content_text="", failures_text="", traceback_text="", sast_text="", tail_text="")
    add_required_or_fail(budget, mandatory_prompt, "Mandatory Execution Report prompt")

    # 9. GENERATED FILE EVIDENCE
    payload = PromptContextBuilder.build_for_report(generated_files, budget)
    content_str = payload.content

    # 10. FAILED / ERROR
    lines = pytest_log.split('\n')
    important_failures = [l for l in lines if 'FAILED' in l or 'ERROR' in l]
    failures_str = "\n".join(important_failures) if important_failures else ""
    failures_str = fit_optional_text(budget, failures_str, "\n... [TRUNCADO FALLOS]")

    # 11. TRACEBACKS
    important_tracebacks = [l for l in lines if 'Traceback' in l]
    tb_str = "\n".join(important_tracebacks) if important_tracebacks else ""
    tb_str = fit_optional_text(budget, tb_str, "\n... [TRUNCADO TRACEBACKS]")

    # 12. SAST ES OPTIONAL Y BOUNDED
    sast_text = fit_optional_text(budget, sast_report, "\n... [SAST TRUNCADO]")

    # 13. PYTEST TAIL ES ÚLTIMA PRIORIDAD
    resto_logs = "\n".join(lines[-50:]) if lines else ""
    tail_text = fit_optional_text(budget, resto_logs, "\n... [TAIL TRUNCADO]")

    # 14. ENSAMBLAJE FINAL
    prompt = build_final_prompt(content_str, failures_str, tb_str, sast_text, tail_text)

    # 15. AJUSTE DE REDONDEO
    limit = 96000
    excess_tokens = len(prompt) // 4 - limit
    while excess_tokens > 0:
        if len(tail_text) > 0:
            trim_chars = max(1, excess_tokens * 4)
            tail_text = tail_text[:-trim_chars]
        elif len(sast_text) > 0:
            trim_chars = max(1, excess_tokens * 4)
            sast_text = sast_text[:-trim_chars]
        elif len(tb_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            tb_str = tb_str[:-trim_chars]
        elif len(failures_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            failures_str = failures_str[:-trim_chars]
        elif len(content_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            content_str = content_str[:-trim_chars]
        else:
            break
        prompt = build_final_prompt(content_str, failures_str, tb_str, sast_text, tail_text)
        excess_tokens = len(prompt) // 4 - limit

    # 16. BARRERA FINAL
    ensure_prompt_fits(prompt, budget, "Execution Report")
    
    # 17. OUTPUT Y FILESYSTEM
    response = runtime.ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt)
    os.makedirs("docs/reports", exist_ok=True)
    report_path = f"docs/reports/run_issue_{issue_id}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write((response.text or "").strip())
    logging.info(f"Reporte guardado en '{report_path}'")
    return report_path

def agent_update_architecture_doc(
    issue_id: int,
    title: str,
    description: str,
    design: dict,
    generated_files: dict[str, str],
    current_arch_doc: str,
    gate_results: list[GateResult],
    git_diff: str,
    runtime: RuntimeClients,
) -> str:
    """Actualiza ARCHITECTURE.md con evidencia real: diff, gates, manifiesto."""
    logging.info("Sincronizando evolucion del manual de arquitectura con evidencia real...")
    arch_file = "docs/ARCHITECTURE.md"

    # ---- PromptBudget con prioridades explicitas ----
    MAX_INPUT = 80000
    RESERVED_OUTPUT = 8192
    budget = PromptBudget(max_input_tokens=MAX_INPUT, reserved_output_tokens=RESERVED_OUTPUT)
    
    # Priority 1: Fixed Instructions
    fixed_instructions = """
    Actuas como un Arquitecto de Soluciones que mantiene el documento 'docs/ARCHITECTURE.md' actualizado.
    Tu tarea es actualizar el documento basandote en la evidencia real de los cambios, no solo en la intencion del diseno.
    INSTRUCCIONES:
    1.  **Actualiza con Evidencia**: Tu principal fuente de verdad es el 'DIFF REAL'. Usalo para entender que interfaces, dependencias y logicas cambiaron realmente.
    2.  **Manten la Estructura**: El documento DEBE seguir esta estructura de 9 secciones.
        1.  `# 1. Vision General del Sistema`
        2.  `# 2. Catalogo de Componentes`
        3.  `# 3. Interfaces Publicas y Contratos`
        4.  `# 4. Flujos de Datos`
        5.  `# 5. Dependencias Externas`
        6.  `# 6. Convenciones de Calidad y Pruebas`
        7.  `# 7. Restricciones Actuales`
        8.  `# 8. Registro de Decisiones de Arquitectura (ADR)`: Crea un nuevo ADR para esta ejecucion.
        9.  `# 9. Historial de Cambios por Issue`: Anade una entrada concisa.
    Devuelve UNICAMENTE el Markdown definitivo.
    """
    try:
        add_required_or_fail(budget, fixed_instructions, "Instrucciones fijas en Architecture Updater")
    except PreflightError as e:
        logging.error(f"Fallo en agente arquitectura: {e}")
        raise

    # Priority 2: Issue metadata obligatorio
    meta = f"Issue: #{issue_id} - {title}\nDescripcion: {description}"
    try:
        add_required_or_fail(budget, meta, "Issue en Architecture Updater")
    except PreflightError as e:
        logging.error(f"Fallo en agente arquitectura: {e}")
        raise

    # Priority 3: Git Diff
    git_diff_text = git_diff or "[Sin diff disponible]"
    diff_toks = len(git_diff_text) // 4
    if not budget.can_add(diff_toks):
        trunc_msg = "\n... [DIFF TRUNCADO]"
        avail = max(0, budget.remaining * 4 - len(trunc_msg) * 4)
        git_diff_text = git_diff_text[:avail] + trunc_msg
        logging.warning("git_diff truncado en Architecture Updater")
        if git_diff_text: budget.add(len(git_diff_text) // 4)
    else:
        budget.add(diff_toks)

    # Priority 4: Manifest
    manifest_text = repr(list(generated_files.keys()))
    if not budget.can_add(len(manifest_text) // 4):
        manifest_text = "[Manifiesto omitido]"
    else:
        budget.add(len(manifest_text) // 4)
        
    # Priority 5: Gate Summary
    gate_summary = repr([{"name": g.name, "passed": g.passed, "executed": g.executed} for g in gate_results])
    if not budget.can_add(len(gate_summary) // 4):
        gate_summary = "[Gate summary omitido]"
    else:
        budget.add(len(gate_summary) // 4)

    # Priority 6: Current Architecture
    arch_display = current_arch_doc or "[El documento esta vacio. Debes crearlo desde cero.]"
    arch_toks = len(arch_display) // 4
    if not budget.can_add(arch_toks):
        trunc_msg = "\n... [ARQUITECTURA TRUNCADA]"
        avail = max(0, budget.remaining * 4 - len(trunc_msg) * 4)
        arch_display = arch_display[:avail] + trunc_msg
        if arch_display: budget.add(len(arch_display) // 4)
    else:
        budget.add(arch_toks)

    # Priority 7: Architecture Justification
    arch_just = design.get("architecture_justification", "[no disponible]")
    if not budget.can_add(len(arch_just) // 4):
        arch_just = "[Justificacion omitida]"
    else:
        budget.add(len(arch_just) // 4)

    prompt = f"""
    {fixed_instructions}

    EVIDENCIA DE CAMBIOS REALIZADOS EN ESTA EJECUCION:
    - {meta}
    - Justificacion de Arquitectura (Intencion Original): {arch_just}
    - Manifiesto Final de Archivos (Creados/Modificados): {manifest_text}
    - Resumen de Quality Gates (solo paso/fallo):
    {gate_summary}

    DIFF REAL DE LOS CAMBIOS (fuente de verdad principal):
    ---
    {git_diff_text}
    ---

    DOCUMENTO DE ARQUITECTURA ACTUAL:
    ---
    {arch_display}
    ---
    """
    
    try:
        ensure_prompt_fits(prompt, budget, "Architecture Updater")
        response = runtime.ai_client.models.generate_content(
            model=MODEL_HEAVY,
            contents=prompt,
        )
        updated_doc = extract_code(response.text or "", "markdown")
        if not updated_doc:
            updated_doc = (response.text or "").strip()
        
        # Write to file
        full_path = arch_file
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(updated_doc)
            
        logging.info(f"Documento de arquitectura actualizado y guardado en {arch_file}.")
        return arch_file
    except Exception as e:
        logging.error(f"Fallo al invocar agente de arquitectura: {e}")
        raise PreflightError(f"Error generando documento de arquitectura: {e}")

def agent_update_user_manual(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], runtime: RuntimeClients) -> str:
    logging.info(f"Evaluando impacto operativo del Issue #{issue_id} en el Manual de Usuario...")
    manual_path = "docs/USER_MANUAL.md"
    existing_content = open(manual_path, "r", encoding="utf-8").read() if os.path.exists(manual_path) else "[Vacio]"
    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)
    
    try:
        # Priority 1: Issue
        add_required_or_fail(budget, title, "Issue title en User Manual")
        
        # Priority 2: description
        add_required_or_fail(budget, description, "Issue desc en User Manual")
        
        # Priority 3: fixed instructions
        fixed_instructions = "Actúas como Technical Writer. Tu tarea es analizar los cambios generados y decidir si impactan la operatividad del usuario final. Si no hay impacto (ej. refactor interno, test), devuelve exactamente el mismo contenido original. Si hay impacto, actualiza el manual de forma incremental, explicando las nuevas funciones sin jerga de implementación. Devuelve el Markdown final completo."
        add_required_or_fail(budget, fixed_instructions, "Instrucciones fijas en User Manual")
        
        # Priority 4: existing manual
        add_required_or_fail(budget, existing_content, "Existing manual")
        
        # Priority 5: cambios generados
        payload = PromptContextBuilder.build_for_docs(design, generated_files, budget)
        cambios_str = payload.content
        
        prompt = f"""
        {fixed_instructions}
        
        ISSUE:
        {title}
        {description}
        
        MANUAL ACTUAL:
        {existing_content}
        
        CAMBIOS GENERADOS:
        {cambios_str}
        
        Devuelve UNICAMENTE el contenido actualizado en Markdown.
        """
        
        ensure_prompt_fits(prompt, budget, "User Manual")
    except PreflightError as e:
        logging.warning(f"User manual omitido por presupuesto: {e}")
        return manual_path
    response = runtime.ai_client.models.generate_content(
        model=MODEL_HEAVY, contents=prompt,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=1024), temperature=0.2)
    )
    clean_text = (response.text or "").strip()
    if clean_text.startswith(f"{MD_FENCE}markdown"): clean_text = clean_text[11:]
    if clean_text.endswith(MD_FENCE): clean_text = clean_text[:-3]
    os.makedirs("docs", exist_ok=True)
    with open(manual_path, "w", encoding="utf-8") as f: f.write(clean_text.strip())
    return manual_path

# =====================================================================
# AGENTE CLÍNICO DE DIAGNÓSTICO DE FALLOS CON GOBERNANZA AUTOMATIZADA
# =====================================================================
def agent_analyze_pipeline_failure(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], gate_results: list[GateResult], runtime: RuntimeClients) -> str:
    logging.warning("El ciclo colapsó. Invocando Diagnóstico Clínico de IA...")
    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=4000)
    
    # 5. CLASIFICACIÓN MANDATORY / OPTIONAL
    gobernanza = """
    Actúas como un Ingeniero Principal de DevOps y Experto en Diagnóstico de Agentes. El pipeline falló tras agotar los reintentos de calidad.
    Realiza una autopsia técnica y emite un reporte Markdown detallado sobre qué causó el bloqueo.
    
    Se preservarán siempre las secciones:
    - FALLO OBSERVADO
    - RIESGO INFERIDO
    - RECOMENDACIÓN PREVENTIVA

    🚨 INSTRUCCIÓN CRÍTICA DE DELEGACIÓN 🚨:
    - Si el fallo es puramente técnico y puede corregirse sin modificar Issue, requisitos, AcceptanceContract, criterios de aceptación o decisiones estructurales: DEBE OMITIR `[ACTION: DELEGATE_TO_PO]`.
    - Si superar el fallo requiere modificar, aclarar o refinar requisitos funcionales, Issue, AcceptanceContract, criterios de aceptación o decisiones estructurales: DEBE INCLUIR obligatoriamente la etiqueta exacta `[ACTION: DELEGATE_TO_PO]` en una línea independiente al final de tu reporte.
    """
    
    issue_ctx = f"Issue #{issue_id}: '{title}' | Spec: {description}"
    
    failed_gates = [g for g in gate_results if not g.passed]
    failed_summaries = "\n".join([f"- Gate Fallido: {g.name}" for g in failed_gates])

    # 7. SINGLE SOURCE OF TRUTH DEL PROMPT
    def build_final_prompt(failed_outputs_text: str, related_files_text: str, other_files_text: str, passed_gates_text: str) -> str:
        return f"""
    {gobernanza}
    
    Contexto: {issue_ctx}
    
    GATES FALLIDOS (CAUSA DEL BLOQUEO):
    {failed_summaries}
    {failed_outputs_text}
    
    CÓDIGO GENERADO RELACIONADO:
    {related_files_text}
    
    RESTO DEL CÓDIGO GENERADO:
    {other_files_text}
    
    GATES EXITOSOS (CONTEXTO):
    {passed_gates_text}
    """

    # 8. RESERVA MANDATORY EXACTA
    mandatory_prompt = build_final_prompt(failed_outputs_text="", related_files_text="", other_files_text="", passed_gates_text="")
    add_required_or_fail(budget, mandatory_prompt, "Mandatory Post-Mortem prompt")

    # 5. RAW EVIDENCE ES LA ÚNICA FUENTE DE CLASIFICACIÓN
    raw_failed_outputs = ""
    for g in failed_gates:
        raw_failed_outputs += f"\n[Output de {g.name}]\n{g.output}\n"

    related_files = []
    other_files = []
    for path in generated_files:
        if path in raw_failed_outputs:
            related_files.append(path)
        else:
            other_files.append(path)
            
    # 6. PRESERVAR UN MANIFIESTO COMPACTO DE CLASIFICACIÓN
    related_paths_raw = "\n".join([f"- `{path}`" for path in related_files])
    other_paths_raw = "\n".join([f"- `{path}`" for path in other_files])
    
    related_paths_str = fit_optional_text(budget, related_paths_raw, "\n... [TRUNCADO PATHS RELACIONADOS]")
    other_paths_str = fit_optional_text(budget, other_paths_raw, "\n... [TRUNCADO PATHS ADICIONALES]")

    # 7. FAILED OUTPUT SIGUE SIENDO EVIDENCIA DE ALTA PRIORIDAD
    failed_outputs = fit_optional_text(budget, raw_failed_outputs, "\n... [TRUNCADO OUTPUT]")
            
    # 9. RELATED CODE SIGUE SIENDO OPTIONAL
    rel_code_str = ""
    for path in related_files:
        code = generated_files[path]
        frag = f"\n### Archivo Relacionado: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n"
        bounded_frag = fit_optional_text(budget, frag, f"\n{MD_FENCE}\n... [TRUNCADO ARCHIVO]")
        if bounded_frag:
            rel_code_str += bounded_frag
            
    # 10. OTHER CODE SIGUE SIENDO OPTIONAL
    oth_code_str = ""
    for path in other_files:
        code = generated_files[path]
        frag = f"\n### Archivo Adicional: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n"
        bounded_frag = fit_optional_text(budget, frag, f"\n{MD_FENCE}\n... [TRUNCADO ARCHIVO]")
        if bounded_frag:
            oth_code_str += bounded_frag
            
    # 14. PASSED GATES SON ÚLTIMA PRIORIDAD
    passed_gates = [g for g in gate_results if g.passed]
    passed_gates_raw = "\n".join([f"- Gate Exitoso: {g.name}" for g in passed_gates])
    passed_gates_str = fit_optional_text(budget, passed_gates_raw, "\n... [TRUNCADO]")
        
    # 11. COMPOSICIÓN DE LAS SECCIONES
    rel_files_str = related_paths_str + rel_code_str
    oth_files_str = other_paths_str + oth_code_str
    
    prompt = build_final_prompt(failed_outputs, rel_files_str, oth_files_str, passed_gates_str)
    
    # 12. ROUNDING LOOP
    limit = budget.max_input_tokens - budget.reserved_output_tokens
    excess_tokens = len(prompt) // 4 - limit
    while excess_tokens > 0:
        if len(passed_gates_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            passed_gates_str = passed_gates_str[:-trim_chars]
        elif len(oth_code_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            oth_code_str = oth_code_str[:-trim_chars]
        elif len(rel_code_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            rel_code_str = rel_code_str[:-trim_chars]
        elif len(failed_outputs) > 0:
            trim_chars = max(1, excess_tokens * 4)
            failed_outputs = failed_outputs[:-trim_chars]
        elif len(other_paths_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            other_paths_str = other_paths_str[:-trim_chars]
        elif len(related_paths_str) > 0:
            trim_chars = max(1, excess_tokens * 4)
            related_paths_str = related_paths_str[:-trim_chars]
        else:
            break
            
        rel_files_str = related_paths_str + rel_code_str
        oth_files_str = other_paths_str + oth_code_str
        prompt = build_final_prompt(failed_outputs, rel_files_str, oth_files_str, passed_gates_str)
        excess_tokens = len(prompt) // 4 - limit

    # 17. BARRERA FINAL
    try:
        ensure_prompt_fits(prompt, budget, "Post-Mortem")
        response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt)
        logging.error(f"REPORTE DE AUTODIAGNÓSTICO POST-MORTEM:\n{(response.text or "").strip()}")
        return (response.text or "").strip()
    except Exception as e: return f"Error de diagnostico: {e}"

# =====================================================================
# AGENTE DE REVISIÓN DE CÓDIGO (NUEVO)
# =====================================================================

def build_coherence_summary(
    generated_files: dict[str, str],
    repo_context,
) -> dict:
    import ast as _ast
    
    # 1. Build virtual index (baseline + generated)
    virtual_index = {}
    for path, summary in {**repo_context.source_index, **repo_context.test_index}.items():
        virtual_index[path] = summary.model_copy()
        
    for path, code in generated_files.items():
        entry = {"signatures": {}, "imports": [], "imported_files": [], "imported_by": [], "_extracted_modules": []}
        try:
            tree = _ast.parse(code, filename=path)
            # simulate extract_ast_signatures
            entry["signatures"] = extract_ast_signatures(tree)
            mod_name = path.replace("\\", "/").replace(".py", "").replace("/", ".")
            entry["_extracted_modules"] = extract_imported_modules(tree, mod_name)
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.Import, _ast.ImportFrom)):
                    try:
                        entry["imports"].append(_ast.unparse(node))
                    except Exception:
                        pass
        except SyntaxError:
            entry["signatures"] = {"__parse_error__": "SyntaxError en contenido final"}
        
        from pydantic import BaseModel
        class MockSummary:
            def __init__(self, **kwargs):
                for k,v in kwargs.items(): setattr(self, k, v)
        virtual_index[path] = MockSummary(signatures=entry["signatures"], imports=entry["imports"], imported_files=[], imported_by=[], _extracted_modules=entry["_extracted_modules"], model_copy=lambda: None)

    # 2. Re-calculate imported_files and imported_by for the WHOLE virtual index
    all_py_files = list(virtual_index.keys())
    
    # Update imported_files for generated files
    for p in generated_files:
        idx = virtual_index[p]
        idx.imported_files = resolve_imported_files(getattr(idx, "_extracted_modules", []), "", all_py_files)
        
    # Reconstruct imported_by for the WHOLE virtual index
    for p, idx in virtual_index.items():
        idx.imported_by = []
        
    for p, idx in virtual_index.items():
        for imp_file in idx.imported_files:
            if imp_file in virtual_index:
                if p not in virtual_index[imp_file].imported_by:
                    virtual_index[imp_file].imported_by.append(p)
                
    # 3. Build summary for generated and affected
    summary = {}
    for p in generated_files:
        idx = virtual_index[p]
        summary[p] = {
            "signatures": idx.signatures,
            "imports": idx.imports,
            "imported_files": list(set(idx.imported_files)),
            "imported_by": list(set(idx.imported_by))
        }
        
    affected_consumers = set()
    for p in generated_files:
        affected_consumers.update(virtual_index[p].imported_by)
        
    for consumer_path in affected_consumers:
        if consumer_path in summary: continue
        if consumer_path not in virtual_index: continue
        idx = virtual_index[consumer_path]
        summary[consumer_path] = {
            "signatures": getattr(idx, "signatures", {}),
            "imports": getattr(idx, "imports", []),
            "imported_files": list(set(getattr(idx, "imported_files", []))),
            "imported_by": list(set(getattr(idx, "imported_by", []))),
            "_source": "existing_consumer",
        }
    return summary


def agent_code_reviewer(design: dict, generated_files: dict[str, str], issue_desc: str, contract: AcceptanceContract, repo_context: RepositoryContext, runtime: RuntimeClients) -> CodeReviewResult:
    """
    Un agente que actua como un revisor de codigo senior.
    Valida que el codigo generado se adhiere semanticamente a las instrucciones.
    """
    logging.info(f"Realizando revision de codigo semantica con {MODEL_HEAVY}...")
    
    all_findings = []
    design_conflict = False

    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)

    # 1. Base mandatory tokens (Contract + Issue)
    contract_json = contract.model_dump_json(indent=2)
    contract_tok = len(contract_json) // 4
    if not budget.can_add(contract_tok):
        return CodeReviewResult(
            approved=False, 
            findings=[ReviewFinding(filepath="unknown", message="Contrato demasiado largo para el reviewer")]
        )
    budget.add(contract_tok)

    issue_tok = len(issue_desc) // 4
    if not budget.can_add(issue_tok):
        return CodeReviewResult(
            approved=False, 
            findings=[ReviewFinding(filepath="unknown", message="Issue demasiado largo para el reviewer")]
        )
    budget.add(issue_tok)

    # 2. Optional context (Architecture, Design, Dependencies)
    arch_doc = repo_context.architecture_document or "[No hay documento de arquitectura]"
    arch_tok = len(arch_doc) // 4
    if arch_tok > 8000:
        arch_doc = arch_doc[:8000 * 4] + "\n... [TRUNCADO]"
        arch_tok = len(arch_doc) // 4
    if budget.can_add(arch_tok):
        budget.add(arch_tok)
    else:
        arch_doc = "[Arquitectura omitida por presupuesto]"

    design_json = json.dumps(design, indent=2)
    des_tok = len(design_json) // 4
    if budget.can_add(des_tok):
        budget.add(des_tok)
    else:
        design_json = "[Diseno omitido por presupuesto]"

    deps_json = json.dumps(repo_context.structured_config.dependencies, indent=2)
    deps_tok = len(deps_json) // 4
    if budget.can_add(deps_tok):
        budget.add(deps_tok)
    else:
        deps_json = "[Dependencias omitidas por presupuesto]"

    base_prompt = f"""
        Actuas como un Ingeniero de Software Principal realizando una revision de codigo. Tu tarea es verificar que el codigo generado cumple ESTRICTAMENTE con todas las fuentes de verdad.

        **FUENTES DE VERDAD (EN ORDEN DE PRIORIDAD):**
        1.  **Requisitos Originales del Issue:**
            {issue_desc}

        2.  **Contrato de Aceptacion (Reglas Estrictas):**
            {contract_json}

        3.  **Documento de Arquitectura (Vision y Restricciones):**
            {arch_doc}

        4.  **Plan del Arquitecto (Intencion de Implementacion):**
            {design_json}

        5.  **Dependencias del Proyecto (Bibliotecas Externas):**
            {deps_json}
    """
    
    # 2000 reserved for the wrapper prompt text below
    available_chunk_tokens = budget.remaining - 2000
    if available_chunk_tokens <= 0:
        return CodeReviewResult(approved=False, findings=[ReviewFinding(filepath="unknown", message="Sin presupuesto para revision.")])

    try:
        payloads = PromptContextBuilder.build_for_reviewer(generated_files, max_tokens=available_chunk_tokens)
    except PreflightError as e:
        return CodeReviewResult(approved=False, findings=[ReviewFinding(filepath="unknown", message=str(e))])
    except Exception as e:
        return CodeReviewResult(approved=False, findings=[ReviewFinding(filepath="unknown", message=f"Fallo al construir chunks: {e}")])
        
    for i, payload in enumerate(payloads):
        prompt = base_prompt + f"""
        **Codigo Generado para Revision (Lote {i+1} de {len(payloads)}):**
        {payload.content}

        IMPORTANTE - ALCANCE DE ESTE LOTE:
        Evalua unicamente el cumplimiento aplicable a los archivos contenidos en este lote ({i+1} de {len(payloads)}).
        No rechaces este lote por la ausencia de archivos que pertenezcan a otros lotes.
        Las reglas del contrato que apunten a archivos no incluidos en este lote se evaluaran en la revision de coherencia transversal final.
        Tu mision es encontrar discrepancias entre el **Codigo Generado** y las **Fuentes de Verdad** para los archivos presentes.
        -   Valida que el codigo cumple con la logica del `issue_desc`.
        -   Valida que el codigo cumple con TODAS las reglas del `AcceptanceContract`, prestando especial atencion a `preserved_behaviors`.
        -   Valida que el codigo no contradice los principios del `architecture_document`.
        -   El `Plan del Arquitecto` es la guia de mas bajo nivel. Si contradice una fuente de verdad superior (Issue, Contrato, Arquitectura), debes rechazar el diseno.

        Si el plan del arquitecto contradice una fuente de verdad superior:
        1. No exijas al codigo cumplir la instruccion contradictoria.
        2. Rechaza el diseno.
        3. Identifica la contradiccion como DESIGN_CONFLICT en tu mensaje.
        
        Responde con un JSON que se ajuste al esquema `CodeReviewResult`. Si todo es correcto, `approved` sera `true`. Si hay fallos, `approved` sera `false` y `findings` contendra una lista de objetos con `filepath` y `message`.
        """
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CodeReviewResult,
            temperature=0.0,
        )
        try:
            ensure_prompt_fits(prompt, budget, "Reviewer Chunk")
            response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
            cleaned_json = extract_code(response.text, "json")
            result = CodeReviewResult.model_validate_json(cleaned_json)
            if not result.approved:
                all_findings.extend(result.findings)
                if result.design_conflict:
                    design_conflict = True
        except Exception as e:
            logging.error(f"Error parseando resultado de code_reviewer: {e}")
            all_findings.append(ReviewFinding(filepath="unknown", message=f"Error en la revision: {e}"))

    # Revision de coherencia transversal
    if generated_files and not all_findings and not design_conflict:
        logging.info("Realizando revision de coherencia transversal del sistema...")

        coherence_budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=4000)
        coherence_graph = build_coherence_summary(generated_files, repo_context)
        coherence_graph_json = json.dumps(coherence_graph, indent=2)
        
        try:
            add_required_or_fail(coherence_budget, contract_json, "Contrato en Coherence")
            add_required_or_fail(coherence_budget, coherence_graph_json, "Grafo en Coherence")
        except PreflightError as e:
            all_findings.append(ReviewFinding(filepath="unknown", message=f"Fallo de presupuesto transversal: {e}"))
            return CodeReviewResult(approved=False, findings=all_findings, design_conflict=design_conflict)

        coherence_prompt = f"""
        Eres un arquitecto de software revisando la coherencia global de un sistema.

        GRAFO DE DEPENDENCIAS Y FIRMAS DEL ESTADO FINAL:
        {coherence_graph_json}

        Contrato de Aceptacion: {contract_json}

        Verifica EXCLUSIVAMENTE:
        1. Imports rotos (un archivo importa simbolos que no existen en sus dependencias).
        2. Interfaces incompatibles (firma esperada por consumidores vs firma real generada).
        3. Archivos contractualmente requeridos ausentes en el manifiesto.
        4. Dependencias circulares evidentes entre los modulos generados.
        5. Consumidores existentes que reciben interfaces incompatibles.

        NO revises el contenido completo de los archivos individuales (ya fue revisado por lotes).
        Responde en JSON bajo el esquema CodeReviewResult.
        """
        
        ensure_prompt_fits(coherence_prompt, coherence_budget, "Coherence Pass")
        try:
            coherence_config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CodeReviewResult,
                temperature=0.0,
            )
            coherence_resp = runtime.ai_client.models.generate_content(model=MODEL_LIGHT, contents=coherence_prompt, config=coherence_config)
            coherence_result = CodeReviewResult.model_validate_json(extract_code(coherence_resp.text, "json"))
            if not coherence_result.approved:
                all_findings.extend(coherence_result.findings)
            if coherence_result.design_conflict:
                design_conflict = True
        except Exception as e:
            logging.error(f"Error en revision de coherencia transversal: {e}")
            all_findings.append(ReviewFinding(
                filepath="__coherence__",
                message=f"La revision de coherencia transversal fallo con un error tecnico: {e}. El pipeline no puede garantizar la integridad del sistema sin esta revision."
            ))

    return CodeReviewResult(approved=len(all_findings)==0, findings=all_findings, design_conflict=design_conflict)

# =====================================================================
# GIT FLOW DE ALTA TRAZABILIDAD CON RUN ID
# =====================================================================
def deploy_to_github(design: dict, generated_files: dict[str, str], report_path: str, arch_path: str, user_manual_path: str, issue_id: int, run_id: str, runtime: RuntimeClients) -> None:
    logging.info("Inicializando PR de alta trazabilidad...")
    commit_title = f"feat(issue-{issue_id}): [{run_id}] refactorizacion y solucion modular evolutiva"
    commit_body = f"Trazabilidad: {run_id}\nJustificacion: {design.get('architecture_justification', '[no disponible]')}"
    
    try:
        # Stage all changes automatically: new files, modifications, and deletions.
        subprocess.run(["git", "add", "-A"], check=True, timeout=60)
        subprocess.run(["git", "commit", "-m", commit_title, "-m", commit_body], check=True, timeout=60)

        # Obtener el hash del commit de implementación
        code_commit_hash = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=60).stdout.strip()

        # Escribir el registro de metadatos con el hash correcto
        write_transactional_metadata(run_id, issue_id, design.get("architecture_justification", "Refactor"), True, design, code_commit_hash)

        # Commit 2: Registro de auditoría
        subprocess.run(["git", "add", "docs/metadata/runs_registry.json"], check=True, timeout=60)
        subprocess.run(["git", "commit", "-m", "chore(audit): register run metadata"], check=True, timeout=60)

        logging.info("Empujando rama de refactorizacion a GitHub...")
        branch_name = f"agent/issue-{issue_id}/{run_id}"
        subprocess.run(["git", "push", "-u", "origin", branch_name], check=True, timeout=300)
        pr = runtime.repo.create_pull(title=f"[Agente SDLC] [{run_id}] Issue #{issue_id}", body=f"Cambio autónomo (Run {run_id}).\nCloses #{issue_id}", head=branch_name, base="main")
        logging.info(f"Pull Request creado: {pr.html_url}")
        try:
            issue = runtime.repo.get_issue(number=issue_id)
            for lbl in ["status:in-progress", "ai:ready-to-code"]:
                if lbl in [l.name for l in issue.labels]: issue.remove_from_labels(lbl)
            try: runtime.repo.get_label("status:pending-review")
            except: runtime.repo.create_label("status:pending-review", "d4c5f9")
            issue.add_to_labels("status:pending-review")
        except Exception: pass
    except Exception:
        logging.exception("Error crítico durante el despliegue.")
        raise
    finally:
        logging.info("Sincronizando entorno con origin...")
        subprocess.run(["git", "fetch", "origin"], capture_output=True, timeout=300)

def ensure_git_setup() -> None:
    logging.info("Verificando Git local...")
    if not os.path.exists(".git"):
        subprocess.run(["git", "init"], check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "checkout", "-b", "main"], check=True, capture_output=True, timeout=60)
    remotes = subprocess.run(["git", "remote"], capture_output=True, text=True, timeout=60)
    if "origin" not in remotes.stdout:
        remote_url = f"https://github.com/{os.getenv('REPO_OWNER')}/{os.getenv('REPO_NAME')}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url], check=True, capture_output=True, timeout=60)
    if subprocess.run(["git", "log", "-1"], capture_output=True, timeout=60).returncode != 0:
        subprocess.run(["git", "fetch", "origin"], capture_output=True, timeout=300)
        subprocess.run(["git", "pull", "origin", "main", "--allow-unrelated-histories", "--no-rebase"], capture_output=True, timeout=300)
    else:
        subprocess.run(["git", "checkout", "main"], check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "pull", "origin", "main"], check=True, capture_output=True, timeout=300)

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
                report = agent_analyze_pipeline_failure(issue_id, title, issue_description, design or {}, generated_files or {}, flat_gates, runtime)
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

def run_pipeline(issue_id: int, run_id: str, run_log_dir: str, runtime: RuntimeClients) -> None:
    context_manager = RepositoryContextManager()
    pipeline_passed = False
    title, desc = "", ""
    design: dict = {}
    generated_files: dict[str, str] = {}
    all_attempt_results: list[list[GateResult]] = []
    flat_gates: list[GateResult] = []
    try:
        issue_to_update = runtime.repo.get_issue(number=issue_id)
        if "ai:ready-to-code" in [l.name for l in issue_to_update.labels]: 
            issue_to_update.remove_from_labels("ai:ready-to-code")
        try: 
            runtime.repo.get_label("status:in-progress")
        except: 
            runtime.repo.create_label("status:in-progress", "fef2c0")
        issue_to_update.add_to_labels("status:in-progress")
    except: 
        pass

    try:
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
        try:
            canonical_contract = agent_generate_acceptance_contract(title, desc, repo_context, runtime)
            logging.info(f"Contrato Canónico generado: {canonical_contract.model_dump_json(indent=2)}")
            _record(GateResult(attempt=1, name="contract_generation", executed=True, passed=True, output="Contrato generado con éxito."))
        except ContractGenerationError as e:
            logging.error(f"Fallo crítico al generar el contrato de aceptación: {e}")
            _record(GateResult(attempt=1, name="contract_generation", executed=True, passed=False, output=str(e)))
            raise

        consistent, consistency_errors = validate_contract_consistency(canonical_contract)
        _record(GateResult(attempt=1, name="contract_consistency", executed=True, passed=consistent, output="\n".join(consistency_errors) if consistency_errors else "Contrato consistente."))
        if not consistent:
            logging.error(f"Inconsistencias lógicas en el contrato: {consistency_errors}")
            raise ContractGenerationError(f"Contrato inconsistente: {consistency_errors}")

        gate_plan = _derive_gate_plan(repo_context, canonical_contract)
        
        policy_errors = validate_testing_policy_compatibility(gate_plan.test_framework, canonical_contract)
        if policy_errors:
            logging.error(f"Fallo en compatibilidad de testing policy: {policy_errors}")
            raise PreflightError(" | ".join(policy_errors))

        tool_errors = tool_preflight(gate_plan)
        _record(GateResult(attempt=1, name="tool_preflight", executed=True, passed=not tool_errors, output="\n".join(tool_errors) if tool_errors else "Herramientas de análisis disponibles."))
        if tool_errors:
            logging.error(f"Fallo en el preflight de herramientas dinámicas: {tool_errors}")
            raise PreflightError(" | ".join(tool_errors))

        contract_capabilities_valid, contract_capabilities_errors = validate_contract_capabilities(canonical_contract, _validator_registry)
        _record(GateResult(attempt=1, name="contract_capabilities_validation", executed=True, passed=contract_capabilities_valid, output="\n".join(contract_capabilities_errors)))
        if not contract_capabilities_valid:
            logging.error(f"El contrato contiene reglas no soportadas por el orquestador: {contract_capabilities_errors}")
            raise ContractGenerationError("Contrato generado con reglas no soportadas.")

        relevant_context_errors = validate_relevant_context_files(repo_context, canonical_contract)
        _record(GateResult(attempt=1, name="relevant_context_validation", executed=True, passed=not relevant_context_errors, output="\n".join(relevant_context_errors) if relevant_context_errors else "Archivos de contexto relevantes validados."))
        if relevant_context_errors:
            logging.error(f"Archivos de contexto relevantes no encontrados: {relevant_context_errors}")
            raise ContractGenerationError(" | ".join(relevant_context_errors))

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
            materialize_cached_files(generated_files, feedback_dict, context_manager)

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
                    logging.info(f"Ejecutando suite de regresión completa de {gate_plan.test_framework}...")
                    if gate_plan.test_framework == "unittest":
                        regression_result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-v"], capture_output=True, text=True, timeout=600)
                    else:
                        regression_result = subprocess.run([sys.executable, "-m", "pytest", "-v"], capture_output=True, text=True, timeout=600)
                    
                    test_passed = regression_result.returncode == 0
                    regression_log = regression_result.stdout + regression_result.stderr
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
                logging.warning("Problema funcional/estructural detectado. Delegando de forma autonoma al PO Agent...")
                try:
                    subprocess.run([sys.executable, "po_agent.py", "--refine-issue", str(issue_id), "--pm-report", pm_report], check=True, timeout=300)

                    # Modificar etiquetas a validacion requerida
                    issue = runtime.repo.get_issue(number=issue_id)
                    if "status:in-progress" in [l.name for l in issue.labels]: 
                        issue.remove_from_labels("status:in-progress")
                    try: 
                        runtime.repo.get_label("po:human-validation-required")
                    except: 
                        runtime.repo.create_label("po:human-validation-required", "fbca04")
                    issue.add_to_labels("po:human-validation-required")
                    logging.info(f"El PO Agent ha renegociado el Issue #{issue_id}. A la espera de firma en GitHub.")
                except Exception as e: 
                    logging.error(f"Fallo al delegar al PO Agent: {e}")
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
    except Exception as pipeline_exc:
        # Flatten any nested gate lists and pass flat_gates which already includes initial_gates
        handle_pipeline_failure(issue_id, title, str(pipeline_exc), run_log_dir, runtime, pipeline_exc, gate_results=flat_gates, design=design, generated_files=generated_files, issue_description=desc)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Framework de Agentes Autonomos SDLC")
    parser.add_argument("--issue", type=int, required=True, help="Numero del Issue a procesar")
    args = parser.parse_args()

    original_cwd = os.getcwd()
    run_id = f"RUN-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    # Define persistent log directory outside the worktree
    run_log_dir = os.path.join(original_cwd, ".agent-runs", run_id)
    os.makedirs(run_log_dir, exist_ok=True)
    
    worktree_dir = os.path.join(".agent-worktrees", run_id)
    
    try:
        # 1. Prepare main repository
        ensure_git_setup()

        # 2. Prepare isolated worktree with its own branch
        branch_name = f"agent/issue-{args.issue}/{run_id}"
        logging.info(f"Creando worktree aislado en '{worktree_dir}' en la rama '{branch_name}'")
        subprocess.run(
            ["git", "worktree", "add", "-b", branch_name, worktree_dir, "origin/main"],
            check=True, capture_output=True, text=True, timeout=120
        )
        
        os.chdir(worktree_dir)
        
        # 3. Build runtime clients (loads .env, validates credentials, opens network connections)
        runtime = build_runtime_clients()

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
        if os.path.exists(worktree_dir):
            logging.info(f"Eliminando worktree: {worktree_dir}")
            subprocess.run(["git", "worktree", "remove", worktree_dir, "--force"], capture_output=True, text=True, timeout=120)
        # Limpiar worktrees residuales
        subprocess.run(["git", "worktree", "prune"], capture_output=True, text=True, timeout=120)
