"""
Product Owner Agent (Compuerta 1 - Olivia's Legacy 2026)
Convierte requisitos funcionales puros en un backlog de Épicas y sub-issues en GitHub.
Usa gobernanza asíncrona nativa mediante etiquetas de aprobación en GitHub.
INCLUYE: Feedback Loop autónomo para refinamiento guiado por Post-Mortem.
NUEVO: Soporte explícito cross-repository (Platform != Target) y Dry-Run.
"""

# Parche de seguridad SSL
import truststore

try:
    truststore.inject_into_ssl()
except AttributeError:
    import urllib3
    truststore.inject_into_urllib3()

import argparse
import ast
import json
import os
import re
import sys
import subprocess
from pathlib import Path

# Fix for Windows console encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')


from dotenv import load_dotenv
from github import Auth, Github
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from typing import Literal
import hashlib

# Constante para evitar cortes en la UI del chat
MD_FENCE = "`" * 3

# =====================================================================
# MONKEY PATCH: CARGA DEL .ENV Y COMPATIBILIDAD SSL (BYPASS)
# =====================================================================
load_dotenv()

if os.getenv("BYPASS_SSL_VERIFY", "false").lower() == "true":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    import requests
    original_request = requests.Session.request
    def patched_request(self, method, url, *args, **kwargs):
        kwargs['verify'] = False
        return original_request(self, method, url, *args, **kwargs)
    requests.Session.request = patched_request

# =====================================================================
# INICIALIZAR CLIENTE GEMINI
# =====================================================================
ai_client = genai.Client()
MODEL_HEAVY = "gemini-3.1-pro-preview"

# =====================================================================
REQUIRED_AUDIT_CHECKS = [
    "REQUIREMENT_SEMANTICS_PRESERVED",
    "ENUMERATED_REQUIREMENT_COMPLETE",
    "SOURCE_REQUIREMENT_MATCH",
    "SOURCE_PRECEDENCE_RESPECTED",
    "PERSISTENCE_SEMANTICS_COMPLETE",
    "NO_RECOMMENDATION_ESCALATION",
    "NO_PRODUCT_ASSUMPTION",
    "AGENT_READY_SCHEMA_COMPLETE",
    "DEPENDENCY_REFERENCES_RESOLVE",
    "DEPENDENCY_COMPLETENESS"
]

AuditCheckName = Literal[
    "REQUIREMENT_SEMANTICS_PRESERVED",
    "ENUMERATED_REQUIREMENT_COMPLETE",
    "SOURCE_REQUIREMENT_MATCH",
    "SOURCE_PRECEDENCE_RESPECTED",
    "PERSISTENCE_SEMANTICS_COMPLETE",
    "NO_RECOMMENDATION_ESCALATION",
    "NO_PRODUCT_ASSUMPTION",
    "AGENT_READY_SCHEMA_COMPLETE",
    "DEPENDENCY_REFERENCES_RESOLVE",
    "DEPENDENCY_COMPLETENESS"
]

AuditVerdict = Literal["PASS", "FAIL"]

class ProposedSubIssue(BaseModel):
    title: str = Field(description="Título claro y descriptivo del Issue.")
    purpose: str = Field(description="Intención funcional. Por qué se hace esto.")
    scope: str = Field(description="Límites de la tarea. Qué incluye.")
    out_of_scope: str = Field(description="Qué NO hacer (fuera del alcance).", default="")
    expected_behavior: str = Field(description="Descripción del comportamiento observable (caja negra).")
    acceptance_criteria: str = Field(description="Criterios verificables y objetivos.")
    constraints: str = Field(description="Restricciones de tecnología o negocio reales.", default="")
    preservation_requirements: str = Field(description="Qué funcionalidad previa NO debe romperse.", default="")
    relevant_context: str = Field(description="Contexto relevante o decisiones previas.", default="")
    unresolved_product_decisions: str = Field(description="SOLO si el producto es genuinamente ambiguo. PROHIBIDO INVENTAR ASUNCIONES.", default="")
    source_inconsistencies: str = Field(description="Omisiones o conflictos de fuentes resueltos vía precedencia. NO asumir funcionalidad.", default="")
    implementation_open_choices: str = Field(description="Decisiones dejadas intencionalmente a la arquitectura (ej. motor de BD exacto, framework) porque la pauta original no obliga una específica.", default="")
    source_requirements: str = Field(description="Trazabilidad SEMÁNTICA OBLIGATORIA. IDs explícitos y porción cubierta. Todo Issue debe tener trazabilidad.")
    depends_on: str = Field(description="Dependencias estrictas y reales. Nombres explícitos de otros Issues. NUNCA usar 'ALL AGENTS' o ambigüedades. Usa 'NONE' si no hay.")
    priority: str = Field(description="Prioridad de desarrollo: 'high', 'medium' o 'low'.")
    estimated_files: list[str] = Field(description="NON-BINDING IMPLEMENTATION HINT: Sugerencias de archivos.", default_factory=list)

class AdversarialAuditFinding(BaseModel):
    check: AuditCheckName = Field(description="Nombre exacto del check.")
    verdict: AuditVerdict = Field(description="PASS o FAIL.")
    evidence: str = Field(description="Evidencia que sustenta el veredicto.")
    affected_issue: str = Field(description="Issue afectado o 'N/A'.")

class BacklogProposal(BaseModel):
    adversarial_self_audit: list[AdversarialAuditFinding] = Field(description="Auto-auditoría adversarial estructurada. Valida estrictamente todos los checks requeridos.")
    epic_title: str = Field(description="Título de la Épica que agrupa el backlog.")
    epic_justification: str = Field(description="Justificación detallada del particionado.")
    proposed_issues: list[ProposedSubIssue] = Field(description="Colección ordenada de sub-issues (Agent-ready).")

def validate_backlog_proposal_deterministic(proposal: BacklogProposal):
    provided_checks = [f.check for f in proposal.adversarial_self_audit]
    missing = set(REQUIRED_AUDIT_CHECKS) - set(provided_checks)
    if missing:
        raise ValueError(f"Audit incomplete. Missing mandatory checks: {missing}")
        
    duplicates = [c for c in set(provided_checks) if provided_checks.count(c) > 1]
    if duplicates:
        raise ValueError(f"Audit invalid. Duplicate checks: {duplicates}")

    fails = [f.check for f in proposal.adversarial_self_audit if f.verdict != "PASS"]
    if fails:
        raise ValueError(f"Audit failed for checks: {fails}")

    validate_proposed_issues_deterministic(proposal.proposed_issues)

def validate_proposed_issues_deterministic(issues: list[ProposedSubIssue]):
    titles = set()
    for sub in issues:
        if not sub.title or not sub.title.strip():
            raise ValueError("Issue title cannot be empty.")
        if sub.title.strip() in titles:
            raise ValueError(f"Duplicate issue title: {sub.title}")
        titles.add(sub.title.strip())
        
        if sub.priority.lower() not in ["high", "medium", "low"]:
            raise ValueError(f"Invalid priority '{sub.priority}' in '{sub.title}'")

    graph = {}
    for sub in issues:
        deps_raw = sub.depends_on
        deps = [d.strip() for d in deps_raw.split(",")] if deps_raw.strip() and deps_raw.upper() not in ["NONE", "N/A", ""] else []
        for dep in deps:
            if dep.upper() in ["ALL AGENTS", "EVERYTHING ABOVE", "TODOS"]:
                raise ValueError(f"Wildcard dependency '{dep}' in '{sub.title}' is not allowed.")
            if dep == sub.title.strip():
                raise ValueError(f"Self-dependency in '{sub.title}'.")
            if dep not in titles:
                raise ValueError(f"Dependency '{dep}' in '{sub.title}' does not resolve to any proposed issue.")
        graph[sub.title.strip()] = deps

    # Dependency cycle check
    def has_cycle(node, visited, stack):
        visited.add(node)
        stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if has_cycle(neighbor, visited, stack):
                    return True
            elif neighbor in stack:
                return True
        stack.remove(node)
        return False
        
    visited = set()
    for node in graph:
        if node not in visited:
            if has_cycle(node, visited, set()):
                raise ValueError("Dependency cycle detected in the backlog.")

# =====================================================================
# TARGET REPOSITORY ISOLATION & VALIDATION
# =====================================================================
def get_git_info(path: str) -> dict:
    try:
        root = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=path, text=True, stderr=subprocess.DEVNULL).strip()
        origin = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=path, text=True, stderr=subprocess.DEVNULL).strip()
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True, stderr=subprocess.DEVNULL).strip()
        branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=path, text=True, stderr=subprocess.DEVNULL).strip()
        return {"root": os.path.normpath(root), "origin": origin, "head": head, "branch": branch}
    except Exception:
        return None

def normalize_remote(remote_url: str) -> str:
    # Soporta HTTPS y SSH
    match = re.search(r'(?:github\.com[:/])(.*?)(?:\.git)?$', remote_url)
    return match.group(1) if match else remote_url

def resolve_target_config(args) -> dict:
    config_path = Path.home() / ".po_target_config.json"
    
    # 1. CLI explícito
    repo = args.target_repo
    workspace = args.target_workspace
    branch = args.target_branch
    
    # 2. Persisted config fallback
    if (not repo or not workspace) and config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                repo = repo or saved.get("target_repo")
                workspace = workspace or saved.get("target_workspace")
                branch = branch or saved.get("target_branch", "main")
        except Exception:
            pass
            
    # 3. Interactive prompt
    if not repo or not workspace:
        if sys.stdin.isatty():
            print("\n[!] Falta configuración de Target Repository.")
            repo = repo or input("GitHub target repository (ej. Oxcalibur/bookai-engine): ").strip()
            workspace = workspace or input("Local target workspace (ruta absoluta): ").strip()
            branch = branch or input(f"Base branch [{branch or 'main'}]: ").strip() or "main"
            
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump({"target_repo": repo, "target_workspace": workspace, "target_branch": branch}, f)
        else:
            print("❌ Error: Missing target configuration in non-interactive mode.")
            sys.exit(1)
            
    return {"repo": repo, "workspace": workspace, "branch": branch or "main"}

def verify_target_identity(config: dict, requirements_file: str = None) -> dict:
    workspace = config["workspace"]
    target_repo = config["repo"]
    base_ref = config["branch"]
    
    platform_info = get_git_info(os.getcwd())
    if not platform_info:
        print("❌ Error: Platform no es un repositorio Git.")
        sys.exit(1)
        
    if not os.path.isdir(workspace):
        print(f"❌ Error: Target workspace no existe: {workspace}")
        sys.exit(1)
        
    target_info = get_git_info(workspace)
    if not target_info:
        print(f"❌ Error: Target workspace no es un repositorio Git: {workspace}")
        sys.exit(1)
        
    if platform_info["root"] == target_info["root"]:
        print("❌ Error: Platform y Target son el mismo repositorio.")
        sys.exit(1)
        
    target_origin = normalize_remote(target_info["origin"])
    if target_origin != target_repo:
        print(f"❌ Error: Target origin mismatch. Esperado: {target_repo}, Actual: {target_origin}")
        sys.exit(1)
        
    # Check base ref and current branch
    if target_info["branch"] != base_ref:
        print(f"❌ Error: Target branch '{target_info['branch']}' no coincide con el base declarado '{base_ref}'.")
        sys.exit(1)
        
    # Check clean working tree
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=workspace, text=True, stderr=subprocess.PIPE).strip()
        if status:
            print(f"❌ Error: Target workspace '{workspace}' no está limpio (tiene archivos modificados o untracked).")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: Falló la verificación de estado git en Target '{workspace}'. {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error crítico verificando estado git: {e}")
        sys.exit(1)
        
    req_path = None
    if requirements_file:
        try:
            req_path = Path(workspace).joinpath(requirements_file).resolve()
            target_root_abs = Path(target_info["root"]).resolve()
            
            # Comprobación estricta de path containment (is_relative_to)
            if not req_path.is_relative_to(target_root_abs):
                print(f"❌ Error: Requirements file '{req_path}' escapa el Target workspace '{target_root_abs}'.")
                sys.exit(1)
                
            if not req_path.exists():
                print(f"❌ Error: Requirements file '{req_path}' no encontrado dentro del Target workspace.")
                sys.exit(1)
                
            req_path = str(req_path)
        except Exception as e:
            print(f"❌ Error resolving requirements path: {e}")
            sys.exit(1)
        
    print("\n" + "="*50)
    print(f"PLATFORM REPOSITORY:\n{platform_info['root']}")
    print(f"PLATFORM BRANCH:\n{platform_info['branch']}")
    print(f"PLATFORM HEAD:\n{platform_info['head']}")
    print(f"\nTARGET GITHUB:\n{target_repo}")
    print(f"TARGET WORKSPACE:\n{target_info['root']}")
    print(f"TARGET ORIGIN:\n{target_origin}")
    print(f"TARGET BASE:\n{base_ref}")
    print(f"TARGET HEAD:\n{target_info['head']}")
    if req_path:
        print(f"REQUIREMENTS:\n{req_path}")
    print(f"PLATFORM != TARGET:\nYES")
    print(f"TARGET IDENTITY VERIFIED:\nYES")
    print("="*50 + "\n")
    
    return {"req_path": req_path, "target_repo": target_repo, "workspace": workspace}

# =====================================================================
# CODEBASE SCANNER
# =====================================================================
class CodebaseScanner:
    """Escanea el Target Repository explícito."""
    def __init__(self, root_path):
        self.root_path = root_path
        self.ignored_dirs = {".git", "venv", "__pycache__", ".pytest_cache", ".env"}

    def get_existing_vocabulary(self) -> str:
        vocab = []
        py_files = []
        test_files = []
        configs = []
        docs = []
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs and not d.startswith('.')]
            for f in files:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, self.root_path)
                
                if f.endswith('.py'):
                    if 'test' in f:
                        test_files.append(rel_path)
                    else:
                        py_files.append(rel_path)
                elif f in ['requirements.txt', 'pyproject.toml', 'pytest.ini', 'setup.py']:
                    configs.append(rel_path)
                elif f.lower().startswith('readme') or f.lower().startswith('architecture') or f.lower().startswith('design') or f.lower().startswith('adr') or (root.endswith('docs') and f.endswith('.md')):
                    docs.append(rel_path)
                    
        vocab.append(f"Project files: {', '.join(configs[:5])}" if configs else "Project files: None")
        vocab.append(f"Docs: {', '.join(docs[:5])}" if docs else "Docs: None")
        vocab.append(f"Test files: {len(test_files)} files found." + (f" ({', '.join(test_files[:3])}...)" if test_files else ""))
        
        classes = []
        funcs = []
        
        for py in py_files[:20]: # Limit bounds
            full = os.path.join(self.root_path, py)
            try:
                with open(full, 'r', encoding='utf-8') as file_obj:
                    content = file_obj.read()
                tree = ast.parse(content)
                for node in ast.iter_child_nodes(tree):
                    if isinstance(node, ast.ClassDef):
                        classes.append(f"Class: {node.name} (in {py})")
                    elif isinstance(node, ast.FunctionDef):
                        args = [a.arg for a in node.args.args]
                        funcs.append(f"Func: {node.name}({', '.join(args)}) (in {py})")
            except Exception:
                pass
                
        if classes:
            vocab.append("Top-level classes (sample):")
            vocab.extend([f"  - {c}" for c in classes[:15]])
        if funcs:
            vocab.append("Top-level functions (sample):")
            vocab.extend([f"  - {f}" for f in funcs[:15]])
            
        if not classes and not funcs and not py_files:
            vocab.append("STATUS: Empty or non-Python repository.")
        else:
            vocab.append("STATUS: Existing repository with code.")
            
        return "\n".join(vocab)

# =====================================================================
# ACCIONES DE GOBERNANZA
# =====================================================================

def get_github_repo(target_repo_name: str, dry_run: bool):
    if dry_run:
        return None
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ Error: GITHUB_TOKEN no está definido para ejecución mutante.")
        sys.exit(1)
    auth = Auth.Token(token)
    github_client = Github(auth=auth)
    return github_client.get_repo(target_repo_name)

def create_labels_if_not_exist(repo, dry_run: bool):
    """Asegura que las etiquetas de gobernanza estén disponibles en GitHub."""
    if dry_run:
        return
        
    labels = {
        "gate:backlog-proposal": "f29513",  # Naranja
        "gate:approved": "0e8a16",          # Verde
        "gate:deployed": "6f42c1",          # Morado
        "ai:ready-to-code": "1d76db",       # Azul
        "po:human-validation-required": "fbca04", # Nuevo: Feedback loop
        "priority:high": "d93f0b",
        "priority:medium": "fbca04",
        "priority:low": "0e8a16"
    }
    for name, color in labels.items():
        try:
            repo.get_label(name)
        except Exception:
            try:
                repo.create_label(name, color)
                print(f"🏷️  [Labels] Creada etiqueta de gobernanza: '{name}'")
            except Exception as e:
                print(f"❌ Error crítico: Fallo al crear la etiqueta '{name}'. Se aborta la operación para evitar estado inconsistente.\n{e}")
                sys.exit(1)

def render_epic_body(proposal: BacklogProposal) -> str:
    epic_body = f"## 🎯 Justificación Arquitectónica del Backlog\n{proposal.epic_justification}\n\n---\n\n"
    epic_body += "## 📋 Propuesta de Sub-Tareas (Agent-Ready Issues)\n\n"
    
    metadata = []
    for idx, sub in enumerate(proposal.proposed_issues, 1):
        epic_body += f"### {idx}. {sub.title} (Prioridad: `{sub.priority.upper()}`)\n"
        epic_body += f"**Purpose:** {sub.purpose}\n\n"
        epic_body += f"**Scope:** {sub.scope}\n\n"
        if sub.out_of_scope:
            epic_body += f"**Out of Scope:** {sub.out_of_scope}\n\n"
        epic_body += f"**Expected Behavior:** {sub.expected_behavior}\n\n"
        epic_body += f"**Acceptance Criteria:**\n{sub.acceptance_criteria}\n\n"
        if sub.constraints:
            epic_body += f"**Constraints:** {sub.constraints}\n\n"
        if sub.preservation_requirements:
            epic_body += f"**Preservation Requirements:** {sub.preservation_requirements}\n\n"
        if sub.relevant_context:
            epic_body += f"**Relevant Context:** {sub.relevant_context}\n\n"
        if sub.unresolved_product_decisions:
            epic_body += f"**Unresolved Product Decisions (AMBIGÜEDAD):** {sub.unresolved_product_decisions}\n\n"
        if getattr(sub, 'source_inconsistencies', None):
            epic_body += f"**Source Inconsistencies:** {sub.source_inconsistencies}\n\n"
        if sub.implementation_open_choices:
            epic_body += f"**Implementation Open Choices:** {sub.implementation_open_choices}\n\n"
        epic_body += f"**Source Requirements:** {sub.source_requirements}\n\n"
        epic_body += f"**Depends On:** {sub.depends_on}\n\n"
        epic_body += f"**Estimated Files (NON-BINDING HINT):** `{', '.join(sub.estimated_files)}`\n\n---\n\n"
        
        metadata.append(sub.model_dump())
        
    comment_open = "<" + "!--"
    comment_close = "--" + ">"
    epic_body += f"\n\n{comment_open} BACKLOG_METADATA_START\n{json.dumps(metadata, indent=2)}\nBACKLOG_METADATA_END {comment_close}"
    return epic_body

def propose_backlog(args):
    """Fase A: Lee requisitos, genera Épica (dry-run o publicación real)."""
    target_config = resolve_target_config(args)
    verified = verify_target_identity(target_config, args.requirements)
    
    with open(verified["req_path"], "r", encoding="utf-8") as f:
        req_text = f.read()
        
    scanner = CodebaseScanner(verified["workspace"])
    existing_vocab = scanner.get_existing_vocabulary()
        
    print("\n🧠 [PO Agent] Analizando requisitos funcionales y diseñando descomposición técnica...")
    
    prompt = f"""
    Actúas como un Product Owner Senior. Tu tarea es generar un Agent-ready Backlog basado en los requisitos.

    📜 DISCIPLINA SEMÁNTICA Y DIRECTIVAS ESTRICTAS:
    1. PRECEDENCIA DE FUENTES OBLIGATORIA: Aplica este orden estricto de autoridad ante conflictos u omisiones:
       1) Requisitos Funcionales/No Funcionales explícitos obligatorios.
       2) Reglas de aceptación/calidad/negocio explícitas.
       3) Constraints arquitectónicos explícitos obligatorios.
       4) Narrativa descriptiva de flujo/arquitectura.
       5) Diagramas, ejemplos y flujos ilustrativos.
       6) Recomendaciones tecnológicas y sugerencias.
       *Regla:* Un requisito de mayor nivel sobrescribe omisiones en diagramas inferiores. Una recomendación nunca es obligatoria.
    2. REQUISITOS ENUMERADOS COMPLETOS: Si un requisito enumera múltiples dimensiones obligatorias, TODAS deben ser observables en los ACs del Issue correspondiente. Ninguna puede omitirse silenciosamente. No agregues capacidades no pedidas.
    3. TRAZABILIDAD Y COHERENCIA SEMÁNTICA: Un ID de requisito no adquiere sentido del Issue. El Issue adquiere sentido del ID. No cites un requisito si su semántica no aplica.
    4. PERSISTENCIA DE DOMINIO: Si el dominio exige persistencia de estado complejo, diferencia: A) esquema, B) mutación en memoria, C) persistencia durable, D) recuperación. Cubrir el esquema no cubre la mutación/persistencia exigidas por el requisito original.
    5. DECISIONES DE PRODUCTO VS INCONSISTENCIAS: `unresolved_product_decisions` es ambigüedad genuina de negocio. `source_inconsistencies` (omisiones resueltas por la precedencia) no bloquean el desarrollo y no son unresolved product decisions. `implementation_open_choices` son para recomendaciones arquitectónicas.
    6. PROHIBIDO INVENTAR ASUNCIONES: No asumas comportamientos por defecto ("se asume que...").
    7. ESQUEMA AGENT-READY MÍNIMO OBLIGATORIO: Todo Issue DEBE tener obligatoriamente `title`, `purpose`, `scope`, `expected_behavior`, `acceptance_criteria`, `source_requirements`, `depends_on`, y `priority`.
    8. DEPENDENCIAS EXPLÍCITAS Y ESTABLES: En `depends_on`, NUNCA uses comodines ("ALL", "TODOS"). Cita el título explícito del Issue exacto.
    9. AUDITORÍA HOSTIL: Tu auto-auditoría DEBE evaluar los issues finales comprobando:
       - REQUIREMENT_SEMANTICS_PRESERVED (must FAIL if an explicitly enumerated mandatory milestone was omitted or generalized)
       - ENUMERATED_REQUIREMENT_COMPLETE (must FAIL if an authoritative explicit list has been shortened, summarized or replaced with "etc.")
       - SOURCE_REQUIREMENT_MATCH
       - SOURCE_PRECEDENCE_RESPECTED
       - PERSISTENCE_SEMANTICS_COMPLETE
       - NO_RECOMMENDATION_ESCALATION
       - NO_PRODUCT_ASSUMPTION (must FAIL if an acceptance/failure condition was converted into an unprovided workflow transition)
       - AGENT_READY_SCHEMA_COMPLETE
       - DEPENDENCY_REFERENCES_RESOLVE
       - DEPENDENCY_COMPLETENESS (must FAIL if Issue text consumes a capability whose provider is missing from depends_on)
       Emite hallazgos estructurados (check, verdict, evidence, affected_issue) y finaliza la lista. NADA de 'Chain of Thought' abierto.
    10. RECONCILIACIÓN DE DOMINIO: Usa nombres de componentes del vocabulario existente si aplican.

    VOCABULARIO EXISTENTE EN TARGET REPOSITORY:
    {existing_vocab}
    
    ESPECIFICACIÓN DE NEGOCIO:
    ---
    {req_text}
    ---
    
    CRITICAL GENERATION RULES PARA ESTRICTA ADHESIÓN:
    1. NO RECOMMENDATION ESCALATION: Si la fuente sugiere o recomienda tecnología, NUNCA la conviertas en obligatoria o en Acceptance Criteria vinculante. Debes listar estas recomendaciones en 'implementation_open_choices' y 'estimated_files'. Toda restricción obligatoria debe ser tecnológicamente neutral (a menos que la fuente indique lo contrario).
    2. DEPENDENCY CONSUMPTION AUDIT: For each proposed Issue, inspect purpose, scope, expected_behavior, and acceptance_criteria. Identify capabilities the Issue directly invokes, consumes, reads from, writes through, mutates through, or requires to execute. If one of those capabilities is delivered by another proposed Issue, that provider Issue MUST appear in depends_on. The audit must compare the text of the consumer Issue against its depends_on field. DEPENDENCY_COMPLETENESS MUST NOT be PASS if Issue text says it consumes capability X AND another proposed Issue provides X AND the provider is absent from depends_on. Do not create dependencies merely because another Issue executes earlier. Dependencies represent capability consumption, not arbitrary sequence. No wildcard dependencies. No artificial "everything above" chains.
    3. COMPOSITE PERSISTENT STATE UPDATE SEMANTICS: Si un requisito autoritativo define un estado compuesto persistente y enumera dimensiones obligatorias, todas las dimensiones enumeradas deben representarse como estado observable mantenible/actualizable donde la fuente requiera mutación.
    4. DETAILED PRODUCT DIMENSIONS: Si un requisito enumera explícitamente granularidad o jerarquía de salida, preserva cada nivel especificado en los criterios de aceptación.
    5. COMPREHENSIVE CONFIGURATION: Si un requisito enumera dimensiones de configuración intercambiables, cada dimensión enumerada debe permanecer configurable y observable. Si el comportamiento/configuración debe ser externo e independiente del código fuente, los Issues de componentes generados deben consumir explícitamente esa capacidad de configuración externa.
    6. ACCEPTANCE CONDITION DOES NOT IMPLY FAILURE TRANSITION: A source rule describing when an output/state/result is valid, accepted, successful, complete, or approved defines an acceptance condition. It does NOT automatically define what the workflow must do when that condition is not satisfied. Never infer, unless an authoritative source explicitly defines it: failure -> retry, failure -> previous component, failure -> next component, failure -> abort, failure -> HITL, failure -> regenerate. If the source explicitly defines the success condition but does NOT unambiguously define the failure transition: 1. preserve the success condition exactly; 2. do not invent the missing transition; 3. record the missing transition in unresolved_product_decisions. A statement that a component 'participates in a cycle' or is subject to a retry limit does not necessarily define the exact routing transition for every possible failure-state combination. Preserve unresolved routing semantics when the exact transition is not explicit.
    7. EXTERNAL INTEGRATION: Si un requisito de integración exige explícitamente múltiples operaciones como crear/escribir/actualizar/leer, preserva cada operación requerida en lugar de debilitarla a un subconjunto.
    8. PHYSICAL MODULARITY: Si la fuente exige separación física de módulos/archivos para un tipo de componente, preserva ese requisito de modularidad física.
    9. ALLOWED SET SELECTION: Si la fuente obliga a usar un conjunto de opciones (ej. YAML o JSON), el conjunto es obligatorio (constraints), pero la selección específica dentro de él es abierta (implementation_open_choices).
    10. ENUMERATED SOURCE FIDELITY: When an authoritative source explicitly enumerates mandatory dimensions, EVERY enumerated dimension must remain explicit in the relevant Issue. Do not replace explicit mandatory enumerations with "etc.", "among others", "such as" when used as a replacement for the complete mandatory list, generic category summaries, or representative subsets. If the source requires A, B, C, D, the resulting relevant Issue must explicitly preserve A, B, C, D. This applies to all mandatory source enumerations, including output dimensions, configuration dimensions, quality dimensions, state dimensions, integration operations, checkpoints, and agent responsibilities.
    11. EXPLICIT MILESTONE COMPLETENESS: When an authoritative requirement explicitly enumerates multiple mandatory human gates, approvals, checkpoints, milestones, or confirmation points, every one must appear explicitly as an observable Acceptance Criterion in the relevant Issue(s). Do not collapse (e.g., Gate A + Gate B into "supports HITL" or another generic abstraction). All explicitly enumerated mandatory milestones must remain individually observable.
    """
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=BacklogProposal,
        temperature=0.2
    )
    
    response = ai_client.models.generate_content(
        model=MODEL_HEAVY,
        contents=prompt,
        config=config
    )
    
    try:
        proposal_obj = BacklogProposal.model_validate_json(response.text or "{}")
        validate_backlog_proposal_deterministic(proposal_obj)
    except Exception as e:
        print(f"❌ Error: La respuesta del LLM no cumple el esquema Pydantic obligatorio o las validaciones deterministas fallaron.\n{e}")
        sys.exit(1)

    print("\n====================================")
    print("ADVERSARIAL SELF-AUDIT (PO-A8)\n")
    for f in proposal_obj.adversarial_self_audit:
        print(f"- {f.check}: [{f.verdict}] {f.evidence} (Issue: {f.affected_issue})")
    print("====================================")

    epic_body = render_epic_body(proposal_obj)
    epic_title = f"[ÉPICA] {proposal_obj.epic_title}"
    
    if args.dry_run:
        print("\n====================================")
        print("EPIC CANDIDATE\n")
        print(f"Title: {epic_title}\n")
        print(epic_body)
        print("====================================")
        print("\nDRY RUN COMPLETE\nGitHub writes: 0\nTarget filesystem writes: 0\nTarget branches created: 0\nOrchestrator executions: 0")
        return

    repo = get_github_repo(verified["target_repo"], args.dry_run)
    create_labels_if_not_exist(repo, args.dry_run)
    
    print("\n📤 [GitHub] Creando Épica de Planificación en el repositorio...")
    epic_issue = repo.create_issue(
        title=epic_title,
        body=epic_body,
        labels=["gate:backlog-proposal"]
    )
    
    print("\n🎉 ¡Propuesta de Backlog publicada con éxito en GitHub!")
    print(f"🔗 URL de la Épica: {epic_issue.html_url}")

def get_issue_fingerprint(sub: ProposedSubIssue) -> str:
    # Deterministic fingerprint using stable dictionary content
    data = sub.model_dump(exclude={"estimated_files"})
    dump = json.dumps(data, sort_keys=True)
    return hashlib.sha256(dump.encode('utf-8')).hexdigest()[:16]

def approve_and_deploy_backlog(args):
    """Fase B: Verifica la etiqueta en la Épica, deserializa, revalida y despliega de forma idempotente."""
    target_config = resolve_target_config(args)
    verify_target_identity(target_config)
    
    epic_id = args.approve_epic
    if args.dry_run:
        print("❌ Error: Dry-run no soportado para approve-epic.")
        sys.exit(1)
        
    repo = get_github_repo(target_config["repo"], args.dry_run)
    create_labels_if_not_exist(repo, args.dry_run)
    print(f"\n🔍 [Gobernanza] Buscando Épica #{epic_id} en {target_config['repo']}...")
    epic_issue = repo.get_issue(number=epic_id)
        
    labels = [label.name for label in epic_issue.labels]
    if "gate:approved" not in labels:
        print(f"🛑 Bloqueado: El Issue #{epic_id} no cuenta con la etiqueta 'gate:approved'.")
        sys.exit(1)
        
    print("🟢 ¡Firma verificada! Deserializando y revalidando especificaciones...")
    
    body = epic_issue.body
    match = re.search("<" + r"!-- BACKLOG_METADATA_START\s*(.*?)\s*BACKLOG_METADATA_END --" + ">", body, re.DOTALL)
    if not match:
        print("❌ Error: No se encontraron metadatos en la Épica.")
        sys.exit(1)
        
    raw_issues = json.loads(match.group(1))
    proposed_issues = []
    try:
        for raw in raw_issues:
            sub = ProposedSubIssue.model_validate(raw)
            proposed_issues.append(sub)
        validate_proposed_issues_deterministic(proposed_issues)
    except Exception as e:
        print(f"❌ Error de revalidación de metadatos aprobados: {e}")
        sys.exit(1)

    # Identidad e Idempotencia
    deployed_signatures = {}
    for issue in repo.get_issues(state='all'): # Sin filtrar por creator
        if issue.body and f"PO_PARENT_EPIC={epic_id}" in issue.body:
            idx_match = re.search(r"PO_CHILD_INDEX=(\d+)", issue.body)
            fp_match = re.search(r"FINGERPRINT=([a-f0-9]+)", issue.body)
            if idx_match and fp_match:
                idx = int(idx_match.group(1))
                if idx in deployed_signatures:
                    print(f"❌ Error crítico de Idempotencia: Índice de hijo duplicado {idx} en la Épica #{epic_id}. Múltiples issues reclaman el mismo índice.")
                    sys.exit(1)
                deployed_signatures[idx] = fp_match.group(1)

    # Validar huellas (fingerprints) antes de crear nada
    missing_indices = []
    for idx, sub in enumerate(proposed_issues, 1):
        fingerprint = get_issue_fingerprint(sub)
        if idx in deployed_signatures:
            if deployed_signatures[idx] != fingerprint:
                print(f"❌ Error crítico de Idempotencia: El Issue {idx} ya existe pero su FINGERPRINT no coincide con la versión aprobada. Deteniendo despliegue.")
                sys.exit(1)
        else:
            missing_indices.append(idx)

    if not missing_indices:
        print("✅ La Épica ya ha sido completamente desplegada (Idempotencia).")
        try:
            epic_issue.add_to_labels("gate:deployed")
            epic_issue.remove_from_labels("gate:backlog-proposal")
        except Exception:
            pass
        return

    for idx in missing_indices:
        sub = proposed_issues[idx - 1]
        fingerprint = get_issue_fingerprint(sub)
            
        title = f"[Épica #{epic_id}] Task {idx}: {sub.title}"
        body_with_epic = f"Este sub-issue ha sido creado bajo la Épica #{epic_id}.\n\n"
        body_with_epic += f"<!-- PO_PARENT_EPIC={epic_id} PO_CHILD_INDEX={idx} FINGERPRINT={fingerprint} -->\n\n"
        body_with_epic += f"**Purpose:** {sub.purpose}\n\n"
        body_with_epic += f"**Scope:** {sub.scope}\n\n"
        if sub.out_of_scope:
            body_with_epic += f"**Out of Scope:** {sub.out_of_scope}\n\n"
        body_with_epic += f"**Expected Behavior:** {sub.expected_behavior}\n\n"
        body_with_epic += f"**Acceptance Criteria:**\n{sub.acceptance_criteria}\n\n"
        if sub.constraints:
            body_with_epic += f"**Constraints:** {sub.constraints}\n\n"
        if sub.preservation_requirements:
            body_with_epic += f"**Preservation Requirements:** {sub.preservation_requirements}\n\n"
        if sub.relevant_context:
            body_with_epic += f"**Relevant Context:** {sub.relevant_context}\n\n"
        if sub.unresolved_product_decisions:
            body_with_epic += f"**Unresolved Product Decisions (AMBIGÜEDAD):** {sub.unresolved_product_decisions}\n\n"
        if getattr(sub, 'source_inconsistencies', None):
            body_with_epic += f"**Source Inconsistencies:** {sub.source_inconsistencies}\n\n"
        if sub.implementation_open_choices:
            body_with_epic += f"**Implementation Open Choices:** {sub.implementation_open_choices}\n\n"
        body_with_epic += f"**Source Requirements:** {sub.source_requirements}\n\n"
        body_with_epic += f"**Depends On:** {sub.depends_on}\n\n"
        body_with_epic += f"**Estimated Files (NON-BINDING HINT):** `{', '.join(sub.estimated_files)}`\n"
        
        created_issue = repo.create_issue(
            title=title,
            body=body_with_epic,
            labels=["ai:ready-to-code", f"priority:{sub.priority.lower()}"]
        )
        print(f"  ↳ ✅ Creado Issue #{created_issue.number}: '{title}'")
        
    try:
        epic_issue.remove_from_labels("gate:backlog-proposal")
    except Exception:
        pass
    try:
        epic_issue.add_to_labels("gate:deployed")
    except Exception:
        pass
    print(f"\n🎉 ¡Gobernanza completada en {target_config['repo']}!")

def refine_issue(args):
    """Fase Feedback Loop."""
    if not getattr(args, 'authorize_refinement', False):
        print("🛑 Bloqueado: El refinamiento autónomo de Issues está deshabilitado por defecto para preservar la frontera de responsabilidad Orchestrator-PO.")
        print("Use --authorize-refinement explícitamente si el ISSUE fue catalogado como semánticamente incorrecto/incompleto, NO solo porque falló la implementación técnica.")
        sys.exit(1)
    if args.dry_run:
        print("❌ Error: Dry-run no soportado para refine-issue.")
        sys.exit(1)
        
    target_config = resolve_target_config(args)
    verify_target_identity(target_config)
    repo = get_github_repo(target_config["repo"], args.dry_run)
    issue_id = args.refine_issue
    pm_report = args.pm_report
    
    print(f"\n[PO-AGENT] 🚨 Refinando Issue #{issue_id} en {target_config['repo']}...")
    issue = repo.get_issue(number=issue_id)
    
    prompt = f"""
    Actúas como Product Owner. El equipo técnico ha devuelto el Issue #{issue_id}.
    POST-MORTEM:
    {pm_report}
    CUERPO ACTUAL:
    {issue.body}
    Reescribe "Criterios de Aceptación Técnicos" resolviendo el Post-Mortem.
    Devuelve ÚNICAMENTE Markdown.
    """
    
    response = ai_client.models.generate_content(
        model=MODEL_HEAVY,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2)
    )
    
    new_body = (response.text or "").strip()
    if new_body.startswith(f"{MD_FENCE}markdown"): new_body = new_body[11:]
    elif new_body.startswith(MD_FENCE): new_body = new_body[3:]
    if new_body.endswith(MD_FENCE): new_body = new_body[:-3]
    
    issue.edit(body=new_body.strip())
    create_labels_if_not_exist(repo, False)
    issue.create_comment("⚠️ **Validación Humana Requerida**: Contrato actualizado tras Post-Mortem.")
    print(f"[PO-AGENT] ✅ Issue #{issue_id} refinado.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PO Agent: Cross-Repository Backlog Generation")
    
    # Core actions
    parser.add_argument("--requirements", type=str, help="Ruta relativa al archivo Markdown en Target")
    parser.add_argument("--approve-epic", type=int, help="Número de Issue de Épica a desplegar")
    parser.add_argument("--refine-issue", type=int, help="Número de Issue a refinar")
    parser.add_argument("--pm-report", type=str, help="Texto del Post-Mortem")
    
    # Target Identity
    parser.add_argument("--target-repo", type=str, help="GitHub repo (ej. Oxcalibur/bookai-engine)")
    parser.add_argument("--target-workspace", type=str, help="Ruta local absoluta al target")
    parser.add_argument("--target-branch", type=str, default="main", help="Base branch del target")
    
    # Mode
    parser.add_argument("--dry-run", action="store_true", help="Evita side effects en GitHub o Filesystem")
    parser.add_argument("--authorize-refinement", action="store_true", help="Autoriza explícitamente la reescritura de un Issue (solo usar si el requisito en sí es incorrecto/incompleto)")
    
    args = parser.parse_args()
    
    if args.requirements:
        propose_backlog(args)
    elif args.approve_epic:
        approve_and_deploy_backlog(args)
    elif args.refine_issue and args.pm_report:
        refine_issue(args)
    else:
        parser.print_help()