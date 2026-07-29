# -*- coding: utf-8 -*-
"""
Orquestador SDLC de Agentes Autónomos con Refactorización Dinámica y Calidad Estática (Versión 2026)
Optimizado para decisiones dinámicas de arquitectura modular libre, Docs-as-Code,
análisis estático contra código muerto (Vulture) y linter (Ruff),
y Git flow con Run ID y registro transaccional JSON de alta trazabilidad.
Incluye un Agente Clínico Post-Mortem y Reflexión Multinivel Integral para auto-corrección estructural.
"""

# 1. PARCHE DE SEGURIDAD SSL INICIAL
import truststore
try:
    truststore.inject_into_ssl()
except AttributeError:
    import urllib3
    truststore.inject_into_urllib3()

import os
import re
import sys
import json
import ast
import datetime
import fnmatch
import hashlib
import logging
import subprocess
from dotenv import load_dotenv

# Constante para evitar cortes en el renderizado de la UI del chat y formatear Prompts
MD_FENCE = "`" * 3

# =====================================================================
# CONFIGURACIÓN DEL LOGGER
# =====================================================================
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s')

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
    logging.info("[Seguridad] Modo de compatibilidad activo: Verificacion SSL de GitHub omitida.")
# =====================================================================

from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError
from github import Github, Auth

# Validar variables críticas
required_env = ["GITHUB_TOKEN", "REPO_OWNER", "REPO_NAME", "GEMINI_API_KEY"]
for var in required_env:
    if not os.getenv(var):
        logging.error(f"La variable de entorno {var} no esta configurada en el .env")
        sys.exit(1)

# 2. Inicializar clientes de API
ai_client = genai.Client()
auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
github_client = Github(auth=auth)
repo_path = f"{os.getenv('REPO_OWNER')}/{os.getenv('REPO_NAME')}"
repo = github_client.get_repo(repo_path)

# --- CONFIGURACION DE MODELOS GEMINI 3 (VIGENCIA 2026) ---
MODEL_HEAVY = "gemini-3.1-pro-preview"   # Razonamiento complejo, refactorizacion estructural y auditorias
MODEL_LIGHT = "gemini-3.5-flash"          # Velocidad extrema para codificacion de piezas, tests y reportes

# =====================================================================
# GESTOR DE CONTEXTO HIBRIDO (ANALISIS ESTATICO DE ARCHIVOS CON AST)
# =====================================================================
class RepositoryContextManager:
    def __init__(self, root_path="."):
        self.root_path = root_path
        self.ignored_dirs = {
            ".git", "venv", "__pycache__", ".pytest_cache", 
            ".env", "node_modules", "dist", "build"
        }

    def generate_repository_map(self) -> str:
        """Genera un mapa textual de la estructura fisica y logica del proyecto."""
        repo_map = []
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            
            relative_path = os.path.relpath(root, self.root_path)
            level = 0 if relative_path == "." else relative_path.count(os.sep) + 1
            indent = "  " * level
            
            if relative_path != ".":
                repo_map.append(f"{indent}[DIR] {os.path.basename(root)}/")
            
            for file in files:
                if file.endswith(".py") and file not in ["orchestrator.py", "po_agent.py", "test_github.py", "test_ssl.py", "user_manual_generator.py"]:
                    file_indent = "  " * (level + 1)
                    repo_map.append(f"{file_indent}[FILE] {file}")
                    
                    full_path = os.path.join(root, file)
                    signatures = self._extract_signatures(full_path)
                    for sig in signatures:
                        repo_map.append(f"{file_indent}  ↳ {sig}")
                        
        return "\n".join(repo_map)

    def get_file_content(self, relative_filepath) -> str:
        """Carga el contenido real de un archivo especifico del repositorio."""
        try:
            full_path = resolve_safe_path(self.root_path, relative_filepath)
            if not os.path.exists(full_path):
                return f"# El archivo '{relative_filepath}' no existe todavia o se creará nuevo."
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"# Error al leer {relative_filepath}: {str(e)}"

    def read_architecture_document(self) -> str:
        """Reads the architecture document if it exists."""
        try:
            path = resolve_safe_path(self.root_path, "docs/ARCHITECTURE.md")
            if not os.path.exists(path):
                logging.info("No se encontró 'docs/ARCHITECTURE.md'. Se procederá sin él.")
                return ""
            with open(path, "r", encoding="utf-8") as file:
                return file.read()
        except (ValueError, IOError) as e:
            logging.warning(f"No se pudo leer el documento de arquitectura: {e}")
            return ""

    def _extract_signatures_from_tree(self, tree: ast.AST) -> list[str]:
        """Extracts class and function signatures from an AST tree."""
        signatures = []
        for child in tree.body:
            if isinstance(child, ast.FunctionDef):
                args = [arg.arg for arg in child.args.args]
                signatures.append(f"def {child.name}({', '.join(args)})")
            elif isinstance(child, ast.ClassDef):
                init_args = []
                methods = []
                for subchild in child.body:
                    if isinstance(subchild, ast.FunctionDef):
                        sub_args = [arg.arg for arg in subchild.args.args if arg.arg != 'self']
                        if subchild.name == "__init__":
                            init_args = sub_args
                        else:
                            methods.append(f"    - def {subchild.name}({', '.join(sub_args)})")
                
                class_def_str = f"class {child.name}"
                if init_args:
                    class_def_str += f"({', '.join(init_args)})"
                
                signatures.append(class_def_str)
                signatures.extend(methods)
        return signatures

    def _scan_config_files(self) -> tuple[dict[str, str], dict[str, str]]:
        """Scans for and reads common project configuration files."""
        project_config_files = [
            "pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg", 
            "mypy.ini", "ruff.toml", ".ruff.toml", "conftest.py"
        ]
        dependency_files = [
            "requirements.txt", "requirements-dev.txt", 
            "poetry.lock", "Pipfile"
        ]
        
        project_configs: dict[str, str] = {}
        dep_files: dict[str, str] = {}

        for filename in project_config_files + dependency_files:
            try:
                path = resolve_safe_path(self.root_path, filename)
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if filename in project_config_files:
                            project_configs[filename] = content
                        else:
                            dep_files[filename] = content
            except (ValueError, IOError):
                pass  # Ignore if file not found or can't be read

        return project_configs, dep_files

    def _analyze_python_file(self, filepath: str) -> "PythonFileSummary | None":
        """Analyzes a single Python file using AST to build a summary."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            tree = ast.parse(content, filename=filepath)
            
            imports, classes, functions, exports = [], [], [], []
            referenced_symbols = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    imports.extend(f"from {module} import {alias.name}" for alias in node.names)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    referenced_symbols.add(node.id)
                elif isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                   isinstance(node.targets[0], ast.Name) and node.targets[0].id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        exports = [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)]

            docstring = ast.get_docstring(tree)
            relative_path = os.path.relpath(filepath, self.root_path).replace("\\", "/")

            return PythonFileSummary(
                filepath=relative_path,
                module_name=relative_path.replace('/', '.').replace('.py', ''),
                is_test="test" in relative_path,
                classes=classes,
                functions=functions,
                signatures=self._extract_signatures_from_tree(tree),
                imports=imports,
                exports=exports,
                docstring_summary=(docstring.split('\n')[0] if docstring else ""),
                referenced_symbols=sorted(list(referenced_symbols)),
                file_hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
                estimated_tokens=len(content) // 4,
            )
        except Exception as e:
            logging.warning(f"No se pudo analizar el archivo Python {filepath}: {e}")
            return None

    def _detect_architecture_conflicts(self, context: "RepositoryContext"):
        """Detects discrepancies between ARCHITECTURE.md and the repository's actual state."""
        if not context.architecture_document:
            return

        conflicts = []
        arch_text = context.architecture_document.lower()
        all_paths = list(context.source_index.keys()) + list(context.test_index.keys())

        # Heuristic 1: Check for mentioned file paths that don't exist.
        mentioned_paths = re.findall(r'[\w/\\-]+\.py', arch_text)
        for path in mentioned_paths:
            normalized_path = path.replace("\\", "/")
            # Ignore common false positives
            if "orchestrator.py" in normalized_path or "po_agent" in normalized_path:
                continue
            
            if normalized_path not in all_paths:
                conflicts.append(ArchitectureConflict(
                    type="MISSING_COMPONENT",
                    description=f"El documento de arquitectura menciona el archivo '{normalized_path}', pero no se encuentra en el repositorio.",
                    architecture_reference=f"Mención de '{path}' en el documento.",
                    repository_evidence=[f"El archivo no existe en el índice del repositorio."],
                ))

        # Heuristic 2: Check for tool usage contradictions.
        if "pytest-mock" in arch_text and ("prescinde" in arch_text or "prohíbe" in arch_text or "no se usa" in arch_text):
            evidence = []
            for file, content in context.dependency_files.items():
                if "pytest-mock" in content:
                    evidence.append(f"`pytest-mock` encontrado en `{file}`")
            
            if evidence:
                conflicts.append(ArchitectureConflict(
                    type="OUTDATED_TOOL_POLICY",
                    description="La arquitectura prohíbe `pytest-mock`, pero está listado como dependencia.",
                    architecture_reference="Se prescinde de librerías de terceros (como `pytest-mock`)",
                    repository_evidence=evidence,
                ))
        
        context.architecture_conflicts = conflicts

    def build_repository_context(self, issue_description: str, budget: "ContextBudget") -> "RepositoryContext":
        """Builds a comprehensive, indexed context of the entire repository."""
        context = RepositoryContext()
        context.repository_map = self.generate_repository_map()
        context.architecture_document = self.read_architecture_document()
        
        source_files = {}
        test_files = {}
        total_tokens = 0
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    summary = self._analyze_python_file(full_path)
                    if summary:
                        total_tokens += summary.estimated_tokens
                        if summary.is_test:
                            test_files[summary.filepath] = summary
                        else:
                            source_files[summary.filepath] = summary
        
        context.source_index = source_files
        context.test_index = test_files
        
        self._link_tests_to_source(context)

        context.project_configuration, context.dependency_files = self._scan_config_files()

        self._detect_architecture_conflicts(context)

        # Progressive context strategy
        if total_tokens <= budget.full_repository_token_limit:
            logging.info(f"El repositorio es pequeño ({total_tokens} tokens). Leyendo todos los archivos Python.")
            for path in context.source_index:
                context.relevant_source_files[path] = self.get_file_content(path)
            for path in context.test_index:
                context.relevant_test_files[path] = self.get_file_content(path)
        else:
            logging.info(f"El repositorio es grande ({total_tokens} tokens). Seleccionando archivos relevantes con un presupuesto de {budget.initial_context_limit} tokens.")
            self.select_relevant_files(
                context, 
                issue_description, 
                budget.initial_context_limit,
                budget.max_relevant_files
            )

        return context

    def _link_tests_to_source(self, context: "RepositoryContext"):
        """Establishes relationships between source and test files based on imports."""
        source_modules = {summary.module_name: summary.filepath for summary in context.source_index.values()}

        for test_path, test_summary in context.test_index.items():
            for imp in test_summary.imports:
                # Example import: "from src.data.besoccer_client import BeSoccerClient"
                # We want to match "src.data.besoccer_client"
                imp_module = imp.split(" import ")[0].replace("from ", "").strip()
                
                if imp_module in source_modules:
                    source_path = source_modules[imp_module]
                    if source_path in context.source_index:
                        source_summary = context.source_index[source_path]
                        
                        if test_path not in source_summary.tested_by:
                            source_summary.tested_by.append(test_path)
                        if source_path not in test_summary.tests_for:
                            test_summary.tests_for.append(source_path)

    def select_relevant_files(
        self,
        context: "RepositoryContext",
        issue_description: str,
        token_budget: int = 4096,
        max_files: int = 20,
    ) -> None:
        """
        Selects the most relevant file contents based on an issue description,
        populating the context's relevant_files fields within a token budget.
        """
        scores: dict[str, float] = {path: 0.0 for path in list(context.source_index.keys()) + list(context.test_index.keys())}
        
        # Combine all text for searching
        search_text = (issue_description + " " + context.architecture_document).lower()
        
        all_summaries = {**context.source_index, **context.test_index}

        # 1. Score based on symbol and path mentions
        for path, summary in all_summaries.items():
            # Score for file path mention
            if summary.filepath.lower() in search_text:
                scores[path] += 10
            # Score for class/function name mentions
            for symbol in summary.classes + summary.functions:
                if symbol.lower() in search_text:
                    scores[path] += 5
        
        # 2. Propagate scores through dependency graph
        for path, summary in all_summaries.items():
            if scores[path] > 0:
                # Boost score of tests for this source file
                for test_path in summary.tested_by:
                    if test_path in scores:
                        scores[test_path] += 3
                # Boost score of source files tested by this test
                for source_path in summary.tests_for:
                    if source_path in scores:
                        scores[source_path] += 3

        # 3. Select files based on score and token budget
        sorted_files = sorted(scores.keys(), key=lambda p: scores[p], reverse=True)
        
        current_tokens = 0
        files_selected = 0
        for path in sorted_files:
            if scores[path] > 0 and files_selected < max_files:
                summary = all_summaries[path]
                if current_tokens + summary.estimated_tokens <= token_budget:
                    content = self.get_file_content(path)
                    if summary.is_test:
                        context.relevant_test_files[path] = content
                    else:
                        context.relevant_source_files[path] = content
                    current_tokens += summary.estimated_tokens
                    files_selected += 1
                else:
                    break # Token budget exceeded

# Instancia global de contexto
context_manager = RepositoryContextManager()
# =====================================================================
# ESQUEMAS PYDANTIC PARA REFACTORIZACION Y DISENO DINAMICO LIBRE
# =====================================================================
class FileAction(BaseModel):
    filepath: str = Field(description="Ruta relativa completa del archivo (ej. 'core/billing.py', 'utils/helpers.py').")
    operation: str = Field(description="Operacion de ciclo de vida: 'CREATE' (crear nuevo), 'MODIFY' (modificar), 'DELETE' (eliminar).")
    file_type: str = Field(description="Categoria: 'production' (logica), 'test' (pytest), 'config', o 'none'.")
    signatures: str = Field(description="Firma de las funciones, metodos o clases que deben residir en este archivo.")
    instructions: str = Field(description="Logica detallada de implementacion o requerimientos de refactorizacion.")

class ProjectDesign(BaseModel):
    architecture_justification: str = Field(description="Razonamiento tecnico completo de por que se adopta esta topologia.")
    actions: list[FileAction] = Field(description="Secuencia ordenada de acciones de archivos a ejecutar fisicamente.")
    dependencies: list[str] = Field(default=[], description="Archivos existentes que se deben leer de forma micro como contexto.")

class ReviewFinding(BaseModel):
    filepath: str
    message: str

class CodeReviewResult(BaseModel):
    approved: bool
    design_conflict: bool = False
    findings: list[ReviewFinding] = Field(default_factory=list)

class SecurityAuditResult(BaseModel):
    approved: bool
    findings: list[str] = Field(default_factory=list)

class ArchitectureConflict(BaseModel):
    type: str = Field(description="Tipo de conflicto (ej. 'MISSING_COMPONENT', 'OUTDATED_TOOL')")
    description: str = Field(description="Descripción del conflicto.")
    architecture_reference: str = Field(description="Cita o referencia del documento de arquitectura.")
    repository_evidence: list[str] = Field(description="Evidencia del repositorio que contradice la arquitectura.")
    blocks_execution: bool = Field(default=False, description="Si el conflicto es tan grave que bloquea la ejecución.")

# Custom Exceptions
class ContractGenerationError(Exception):
    """Custom exception for failures during acceptance contract generation."""
    pass
class RequiredCall(BaseModel):
    name: str
    count: int = 1

class FileContract(BaseModel):
    filepath: str
    required_symbols: list[str] = Field(default_factory=list)
    preserved_symbols: list[str] = Field(default_factory=list)
    required_exports: list[str] = Field(default_factory=list)
    required_imports: list[str] = Field(default_factory=list)
    forbidden_imports: list[str] = Field(default_factory=list)
    required_calls: dict[str, list[RequiredCall]] = Field(default_factory=dict)
    forbidden_constructs: list[str] = Field(default_factory=list)
    required_patterns: list[str] = Field(default_factory=list)

class ContextBudget(BaseModel):
    full_repository_token_limit: int = 40_000
    initial_context_limit: int = 25_000
    expansion_limit: int = 15_000
    max_dependency_depth: int = 2
    max_relevant_files: int = 20

class PythonFileSummary(BaseModel):
    filepath: str
    module_name: str
    is_test: bool
    classes: list[str]
    functions: list[str]
    signatures: list[str]
    imports: list[str]
    exports: list[str]
    docstring_summary: str
    referenced_symbols: list[str]
    file_hash: str
    estimated_tokens: int
    tests_for: list[str] = Field(default_factory=list, description="List of source files this file tests.")
    tested_by: list[str] = Field(default_factory=list, description="List of test files that cover this source file.")

class RepositoryContext(BaseModel):
    repository_map: str = ""
    architecture_document: str = ""
    source_index: dict[str, PythonFileSummary] = Field(default_factory=dict)
    test_index: dict[str, PythonFileSummary] = Field(default_factory=dict)
    project_configuration: dict[str, str] = Field(default_factory=dict)
    dependency_files: dict[str, str] = Field(default_factory=dict)
    detected_test_framework: str | None = None
    detected_quality_tools: list[str] = Field(default_factory=list)
    relevant_source_files: dict[str, str] = Field(default_factory=dict)
    relevant_test_files: dict[str, str] = Field(default_factory=dict)
    architecture_conflicts: list["ArchitectureConflict"] = Field(default_factory=list)

class AcceptanceContract(BaseModel):
    required_final_files: set[str] = Field(default_factory=set, description="Archivos que deben existir al finalizar la tarea.")
    required_new_files: set[str] = Field(default_factory=set, description="Archivos que deben ser creados.")
    required_modified_files: set[str] = Field(default_factory=set, description="Archivos que deben ser modificados.")
    required_deleted_files: set[str] = Field(default_factory=set, description="Archivos que deben ser eliminados.")
    preserved_files: set[str] = Field(default_factory=set, description="Archivos existentes que son relevantes pero no deben ser modificados.")
    relevant_context_files: set[str] = Field(default_factory=set, description="Archivos existentes que son relevantes como contexto para la generación de código.")

    required_tests: dict[str, list[str]] = Field(default_factory=dict)
    protected_tests: dict[str, list[str]] = Field(default_factory=dict, description="Tests existentes que no deben romperse ni eliminarse.")
    preserved_symbols: dict[str, list[str]] = Field(default_factory=dict, description="Símbolos (clases, funciones) cuyas firmas deben preservarse.")
    preserved_behaviors: list[str] = Field(default_factory=list, description="Comportamientos existentes descritos en lenguaje natural que no deben romperse.")

    forbidden_test_names: list[str] = Field(default_factory=list)
    forbidden_constructs: dict[str, list[str]] = Field(default_factory=dict, description="Pattern: {filepath_glob: [construct_name]}")
    required_exports: dict[str, list[str]] = Field(default_factory=dict)
    required_tools: list[str] = Field(default_factory=list)

    # New structured fields for deterministic validation
    required_imports: dict[str, list[str]] = Field(default_factory=dict, description="Pattern: {filepath_glob: ['from module import item']}")
    forbidden_imports: dict[str, list[str]] = Field(default_factory=dict, description="Pattern: {filepath_glob: ['module_name']}")
    required_calls: dict[str, dict[str, list[RequiredCall]]] = Field(default_factory=dict, description="{filepath: {caller_func: [{'name': 'callee', 'count': 1}]}}")
    required_patterns: dict[str, list[str]] = Field(default_factory=dict, description="{filepath: ['log_before_raise']}")
    required_structures: dict[str, dict[str, str]] = Field(default_factory=dict, description="{filepath: {var_name: 'has_aliases'}}")
    required_decorators: dict[str, list[str]] = Field(default_factory=dict, description="{filepath: ['decorator_name']}")
class GateResult(BaseModel):
    attempt: int
    name: str
    executed: bool
    passed: bool | None = None
    output: str = ""


# =====================================================================
# REGISTRO DE CAPACIDADES DEL VALIDADOR DE CONTRATOS
# =====================================================================
_SUPPORTED_AST_CONSTRUCTS = {"continue", "pass"}
_SUPPORTED_CODE_PATTERNS = {"log_before_raise"}
_SUPPORTED_STRUCTURE_CHECKS = {"has_aliases"}

_validator_registry = {
    "forbidden_constructs": _SUPPORTED_AST_CONSTRUCTS,
    "required_patterns": _SUPPORTED_CODE_PATTERNS,
    "required_structures": _SUPPORTED_STRUCTURE_CHECKS,
    "required_final_files": True,
    "required_new_files": True,
    "required_modified_files": True,
    "required_deleted_files": True,
    "preserved_files": True,
    "relevant_context_files": True,
    "required_tests": True,
    "protected_tests": True,
    "preserved_symbols": True,
    "preserved_behaviors": True,
    "forbidden_test_names": True,
    "required_exports": True,
    "required_tools": True,
    "required_imports": True,
    "forbidden_imports": True,
    "required_calls": True,
    # 'required_decorators' is intentionally omitted to test the validation
}


def validate_contract_capabilities(contract: AcceptanceContract, registry: dict) -> tuple[bool, list[str]]:
    """
    Valida que el contrato de aceptación solo use reglas y constructos
    soportados por el motor de validación AST.
    """
    errors = []

    # Check for specific unsupported values within supported fields
    for path_glob, constructs in contract.forbidden_constructs.items():
        for construct in constructs:
            if construct not in registry.get("forbidden_constructs", set()):
                errors.append(f"Contrato usa un 'forbidden_construct' no soportado: '{construct}' en '{path_glob}'. Soportados: {sorted(list(registry.get('forbidden_constructs', set())))}")

    for path_glob, patterns in contract.required_patterns.items():
        for pattern in patterns:
            if pattern not in registry.get("required_patterns", set()):
                errors.append(f"Contrato usa un 'required_pattern' no soportado: '{pattern}' en '{path_glob}'. Soportados: {sorted(list(registry.get('required_patterns', set())))}")

    for path_glob, structures in contract.required_structures.items():
        for var_name, check_type in structures.items():
            if check_type not in registry.get("required_structures", set()):
                errors.append(f"Contrato usa un 'required_structure' check no soportado: '{check_type}' para '{var_name}' en '{path_glob}'. Soportados: {sorted(list(registry.get('required_structures', set())))}")

    # Check for entire fields that are not supported by the registry
    for field in contract.model_fields:
        if field not in registry:
            field_value = getattr(contract, field)
            if field_value:  # Only report if the unsupported field is actually used
                errors.append(f"Contrato usa un campo no soportado por el validador: '{field}'.")

    return not errors, errors


def _create_file_contract(filepath: str, contract: AcceptanceContract) -> "FileContract":
    """Extracts a file-specific contract from the global acceptance contract."""
    
    file_contract = FileContract(filepath=filepath)
    
    # preserved_symbols
    if filepath in contract.preserved_symbols:
        file_contract.preserved_symbols = contract.preserved_symbols[filepath]
        
    # required_exports
    if filepath in contract.required_exports:
        file_contract.required_exports = contract.required_exports[filepath]

    # required_imports
    for path_glob, imports in contract.required_imports.items():
        if fnmatch.fnmatch(filepath, path_glob):
            file_contract.required_imports.extend(imports)
            
    # forbidden_imports
    for path_glob, imports in contract.forbidden_imports.items():
        if fnmatch.fnmatch(filepath, path_glob):
            file_contract.forbidden_imports.extend(imports)
            
    # required_calls
    if filepath in contract.required_calls:
        file_contract.required_calls = contract.required_calls[filepath]
        
    # forbidden_constructs
    for path_glob, constructs in contract.forbidden_constructs.items():
        if fnmatch.fnmatch(filepath, path_glob):
            file_contract.forbidden_constructs.extend(constructs)
            
    # required_patterns
    if filepath in contract.required_patterns:
        file_contract.required_patterns = contract.required_patterns[filepath]
        
    return file_contract

def agent_generate_acceptance_contract(title: str, description: str, repository_context: RepositoryContext) -> AcceptanceContract:
    """
    Generates a structured acceptance contract from the issue description, repository context, and architecture.
    """
    logging.info("Generando Contrato de Aceptación a partir del Issue y contexto del repositorio...")
    
    source_index_json = json.dumps({fp: summary.model_dump(exclude={'file_hash', 'estimated_tokens', 'referenced_symbols', 'imports', 'docstring_summary'}) for fp, summary in repository_context.source_index.items()}, indent=2)
    
    prompt = f"""
    Actúas como un Quality Assurance Lead y Arquitecto de Pruebas. Tu tarea es leer una especificación de requisitos de un Issue y traducirla a un contrato de aceptación técnico y estricto en formato JSON.

    Este contrato define las reglas inmutables que el código generado debe cumplir.

    FUENTES DE INFORMACIÓN:
    1. REQUISITOS DEL ISSUE (El 'qué' se debe cambiar):
       - Título: {title}
       - Requisitos: {description}

    2. DOCUMENTO DE ARQUITECTURA (El 'porqué' de las decisiones de diseño):
       --- INICIO DOCUMENTO ---
       {repository_context.architecture_document if repository_context.architecture_document else "[No se encontró documento de arquitectura.]"}
       --- FIN DOCUMENTO ---

    3. ÍNDICE DEL CÓDIGO FUENTE (El estado 'real' del código):
       --- INICIO ÍNDICE FUENTE ---
       {source_index_json}
       --- FIN ÍNDICE FUENTE ---

    Analiza TODAS las fuentes de información para derivar el contrato. Por ejemplo:
    - Si el Issue pide modificar un archivo, el contrato debe incluirlo en `required_files`.
    - Si la arquitectura prohíbe `pytest-mock`, el contrato debe reflejarlo en `forbidden_imports`.
    - Si el Issue menciona una funcionalidad que ya tiene tests, el contrato debe listarlos en `required_tests` para asegurar que no se rompan.
    - Si el código existente usa un patrón (ej. `logger.warning` antes de `raise`), el contrato debe exigirlo en `required_patterns`.

    Extrae las siguientes reglas:
    - `required_final_files`: Archivos que deben existir al finalizar la tarea.
    - `required_new_files`: Archivos que deben ser creados.
    - `required_modified_files`: Archivos que deben ser modificados.
    - `required_deleted_files`: Archivos que deben ser eliminados.
    - `preserved_files`: Archivos existentes que son relevantes pero no deben ser modificados.
    - `relevant_context_files`: Archivos de contexto relevantes.
    - `required_tests`: Pruebas obligatorias para la **nueva** funcionalidad.
    - `protected_tests`: Tests existentes que no deben romperse ni eliminarse. Extrae esto del índice del repositorio, especialmente los tests que cubren los módulos a modificar.
    - `forbidden_test_names`: Nombres de pruebas que están explícitamente prohibidos.
    - `preserved_symbols`: Símbolos (clases, funciones) cuyas firmas deben preservarse porque otros módulos dependen de ellas. Extrae esto del índice y del documento de arquitectura.
    - `preserved_behaviors`: Comportamientos existentes descritos en lenguaje natural que no deben romperse. Extrae esto del documento de arquitectura y de los requisitos del Issue.
    - `forbidden_constructs`: Un diccionario donde la clave es un glob de ruta de archivo (ej. `src/data/besoccer*.py`) y el valor es una lista de constructos prohibidos ('continue', 'pass').
    - `required_exports`: Símbolos que deben estar en `__all__`.
    - `required_calls`: Especifica que una función debe llamar a otra. Ej: `{"src/data/cement_dictionary.py": {"normalize_team_name": [{"name": "strip", "count": 1}, {"name": "lower", "count": 1}]}}`.
    - `required_patterns`: Patrones de código obligatorios. Ej: `{"src/data/besoccer_client.py": ["log_before_raise"]}`.
    - `required_structures`: Validaciones sobre estructuras de datos. Ej: `{"src/data/cement_dictionary.py": {"TEAM_MAPPING": "has_aliases"}}`.
    - `required_imports` / `forbidden_imports`: Reglas sobre importaciones. Ej: `{"tests/*": ["from unittest.mock import patch"]}` y `{"tests/*": ["pytest_mock"]}`.
    - `required_tools`: Herramientas específicas que deben o no deben usarse (ej. "usar unittest.mock.patch", "no usar pytest-mock").

    Si un campo no es aplicable, déjalo como una lista o diccionario vacío.
    Responde únicamente con el JSON que se ajuste al esquema `AcceptanceContract`.
    """
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AcceptanceContract,
        temperature=0.1
    )
    
    try:
        response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
        contract = AcceptanceContract.model_validate_json(response.text)
        logging.info("Contrato de Aceptación generado con éxito.")
        return contract
    except (json.JSONDecodeError, ValidationError, Exception) as e:
        logging.error(f"No se pudo generar o validar el Contrato de Aceptación: {e}")
        raise ContractGenerationError(f"Fallo crítico al generar el Contrato de Aceptación: {e}") from e
        # Return a default/empty contract on failure to avoid crashing the pipeline
        return AcceptanceContract()

def extract_code(text, language="python"):
    """
    Extrae el contenido de un bloque de código Markdown.
    Si no encuentra un bloque, devuelve el texto limpio.
    """
    # Intenta extraer JSON si el texto parece un objeto o array JSON
    stripped_text = text.strip()
    if (stripped_text.startswith('{') and stripped_text.endswith('}')) or \
       (stripped_text.startswith('[') and stripped_text.endswith(']')):
        try:
            json.loads(stripped_text)
            return stripped_text
        except json.JSONDecodeError:
            pass # No es JSON válido, seguir con la lógica de markdown

    pattern = rf"{MD_FENCE}{language}\s*(.*?)\s*{MD_FENCE}"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return text.strip()

# =====================================================================
# FUNCION DE LOGS LOCALES Y METADATOS TRANSACCIONALES
# =====================================================================
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
def run_static_analysis(generated_filepaths):
    """
    Ejecuta Ruff (Auto-fix + Linter) y Vulture (detector de código muerto)
    de forma nativa sobre los archivos generados en disco.
    Filtra los archivos de pruebas unitarias de Vulture para mitigar falsos positivos.
    """
    success = True
    report = ""
    
    py_files = [f for f in generated_filepaths if f.endswith(".py") and os.path.exists(f)]
    if not py_files: return True, "No hay archivos Python para validacion estatica."
        
    # Files for Ruff should not include the whitelist, as it contains non-standard Python for Vulture.
    ruff_files = [f for f in py_files if "vulture_whitelist.py" not in f]

    logging.info(f"Ejecutando Auto-Fixer y analizando archivos con Ruff ({len(ruff_files)}) y Vulture...")
    try:
        # 1 y 2. Ejecutar Ruff Check con auto-fix nativo para estilo en todo el ecosistema
        for filepath in ruff_files:
            subprocess.run([sys.executable, "-m", "ruff", "check", "--fix", filepath], capture_output=True, text=True, timeout=300)
        for filepath in ruff_files:
            result = subprocess.run([sys.executable, "-m", "ruff", "check", filepath], capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                success = False
                report += f"\n[Ruff Check] Errores de estilo criticos en '{filepath}':\n{result.stdout or result.stderr}"
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        success = False
        report += f"\n[Fallo de Infraestructura] No se pudo ejecutar Ruff: {e}. Asegúrate de que está instalado y en el PATH."
            
    # 3. Ejecutar Vulture (Detector de codigo muerto) EXCLUSIVAMENTE en archivos de produccion lógicos
    # Vulture will analyze all python files that are not tests. This correctly includes the whitelist.
    prod_files = [f for f in py_files if "test_" not in f and "tests/" not in f]
    if prod_files:
        try:
            result_v = subprocess.run([sys.executable, "-m", "vulture"] + prod_files, capture_output=True, text=True, timeout=300)
            if result_v.returncode != 0:
                success = False
                report += f"\n[Vulture Detector] Codigo muerto detectado:\n{result_v.stdout or result_v.stderr}"
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            success = False
            report += f"\n[Fallo de Infraestructura] No se pudo ejecutar Vulture: {e}. Asegúrate de que está instalado y en el PATH."
        
    return success, report

def reload_code_after_ruff(generated_files: dict[str, str]) -> None:
    for path in generated_files:
        if os.path.exists(path):
            generated_files[path] = context_manager.get_file_content(path)

# =====================================================================
# CAPA DE VALIDACIÓN DE CALIDAD DE CÓDIGO (NUEVO)
# =====================================================================
def validate_code_quality(code: str, filepath: str) -> tuple[bool, str]:
    """
    Valida la sintaxis y el cumplimiento de políticas de tipado estricto usando AST.
    Retorna (es_valido: bool, mensaje_error: str).
    """
    # 1. Verificación de sintaxis básica
    try:
        tree = ast.parse(code, filename=filepath)
    except SyntaxError as se:
        return False, f"ERROR DE SINTAXIS: El código no es Python válido. Detalle: {se}"

    # 2. Verificación de Type Hints en todas las funciones y métodos
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Validar argumentos
            for arg in node.args.args:
                if arg.arg not in ('self', 'cls') and arg.annotation is None:
                    errors.append(f"Argumento '{arg.arg}' en la función '{node.name}' (línea {arg.lineno}) no tiene type hint.")
            # Validar retorno (excepto en constructores)
            if node.returns is None and node.name != '__init__':
                errors.append(f"La función '{node.name}' (línea {node.lineno}) no tiene un type hint de retorno (ej: -> str).")

    if errors:
        return False, "ERROR DE CALIDAD DE CÓDIGO (FALTA DE TIPADO ESTRICTO):\n" + "\n".join(errors)

    return True, ""

def parse_compiler_output(log: str) -> dict[str, str]:
    """Parses linter/compiler output (like MyPy) to group messages by filepath."""
    feedback_map: dict[str, list[str]] = {}
    # Regex to capture file paths, including Windows drive letters.
    pattern = re.compile(r"^((?:[A-Za-z]:)?[^:]*?\.py):\d+(?::\d+)?:")

    for line in log.splitlines():
        if not line.strip():
            continue
        
        match = pattern.match(line)
        if match:
            filepath = match.group(1)
            
            # Convert to relative path if it's absolute
            if os.path.isabs(filepath):
                try:
                    filepath = os.path.relpath(filepath, start=os.getcwd())
                except ValueError:
                    # This can happen on Windows if the path is on a different drive.
                    pass

            # Normalize path separators for consistency
            filepath = filepath.replace("\\", "/")

            if filepath not in feedback_map:
                feedback_map[filepath] = []
            feedback_map[filepath].append(line)

    if not feedback_map:
        return {"all": log}

    return {filepath: "\n".join(messages) for filepath, messages in feedback_map.items()}

def _check_forbidden_constructs(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    errors = []
    construct_map = {
        "continue": ast.Continue,
        "pass": ast.Pass,
    }
    for path_glob, constructs in contract.forbidden_constructs.items():
        if fnmatch.fnmatch(filepath, path_glob):
            for construct_name in constructs:
                if construct_name in construct_map:
                    for node in ast.walk(tree):
                        if isinstance(node, construct_map[construct_name]):
                            errors.append(f"Constructo prohibido '{construct_name}' encontrado en {filepath} en la línea {node.lineno}")
    return errors

def _check_exports(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    if filepath not in contract.required_exports:
        return []
    
    expected_exports = set(contract.required_exports[filepath])
    found_all = False
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and \
           isinstance(node.targets[0], ast.Name) and node.targets[0].id == "__all__":
            if isinstance(node.value, (ast.List, ast.Tuple)):
                actual_exports = {elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)}
                if expected_exports == actual_exports:
                    found_all = True
                    break
    if not found_all:
        return [f"`__all__` en {filepath} no coincide con el contrato. Se esperaba: {sorted(list(expected_exports))}"]
    return []

def _check_tests(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    # Un archivo se considera de prueba si está en `required_tests` o `protected_tests`.
    # La validación de `forbidden_test_names` se aplica a ambos.
    if filepath not in contract.required_tests and filepath not in contract.protected_tests:
        return []
    
    errors = []
    test_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    
    if filepath in contract.required_tests:
        for required_test in contract.required_tests[filepath]:
            if required_test not in test_names:
                errors.append(f"Falta la prueba obligatoria por contrato: {required_test}")
    
    for forbidden_test in contract.forbidden_test_names:
        if forbidden_test in test_names:
            errors.append(f"Se encontró un test prohibido por el contrato: {forbidden_test}")
    return errors

def _check_imports(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    errors = []
    # Check forbidden imports
    for path_glob, forbidden_list in contract.forbidden_imports.items():
        if fnmatch.fnmatch(filepath, path_glob):
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name in forbidden_list:
                            errors.append(f"Import prohibido '{alias.name}' encontrado en {filepath}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module and node.module in forbidden_list:
                        errors.append(f"Import prohibido del módulo '{node.module}' encontrado en {filepath}")
    return errors

def _check_patterns(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    errors = []
    if filepath in contract.required_patterns:
        for pattern in contract.required_patterns[filepath]:
            if pattern in _SUPPORTED_CODE_PATTERNS:
                for node in ast.walk(tree):
                    if isinstance(node, ast.ExceptHandler):
                        raise_node = next((item for item in node.body if isinstance(item, ast.Raise)), None)
                        if raise_node:
                            log_call_found = False
                            for item in node.body:
                                if item.lineno >= raise_node.lineno:
                                    break
                                if isinstance(item, ast.Expr) and isinstance(item.value, ast.Call):
                                    call = item.value
                                    if isinstance(call.func, ast.Attribute) and call.func.attr == 'warning':
                                        log_call_found = True
                                        break
                            if not log_call_found:
                                errors.append(f"Falta una llamada a 'logger.warning' antes de 'raise' en un bloque except en la línea {raise_node.lineno} de {filepath}")
            else:
                errors.append(f"Patrón requerido '{pattern}' en {filepath} no está implementado o soportado por el validador AST.")
    return errors

def _check_calls(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    errors = []
    if filepath in contract.required_calls:
        for func_name, required_calls in contract.required_calls[filepath].items():
            for func_node in ast.walk(tree):
                if isinstance(func_node, ast.FunctionDef) and func_node.name == func_name:
                    for call_info in required_calls:
                        callee_name = call_info.name
                        required_count = call_info.count
                        
                        actual_count = 0
                        for call_node in ast.walk(func_node):
                            if isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Name) and call_node.func.id == callee_name:
                                actual_count += 1
                            elif isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Attribute) and call_node.func.attr == callee_name:
                                actual_count += 1
                        
                        if actual_count < required_count:
                            errors.append(f"En {filepath}, la función '{func_name}' debe llamar a '{callee_name}' al menos {required_count} veces, pero solo se encontraron {actual_count}.")
    return errors

def _check_structures(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    errors = []
    if filepath in contract.required_structures:
        for var_name, check_type in contract.required_structures[filepath].items():
            if check_type in _SUPPORTED_STRUCTURE_CHECKS:
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == var_name:
                                if not isinstance(node.value, ast.Dict):
                                    errors.append(f"La estructura '{var_name}' en {filepath} no es un diccionario.")
                                    continue
                                values = [elt.value for elt in node.value.values if isinstance(elt, ast.Constant)]
                                if len(values) == len(set(values)):
                                    errors.append(f"La estructura '{var_name}' en {filepath} no contiene alias (valores duplicados).")
            else:
                errors.append(f"Validación de estructura '{check_type}' para '{var_name}' en {filepath} no está implementada o soportada por el validador AST.")
    return errors

def validate_contractual_ast(code: str, filepath: str, contract: AcceptanceContract) -> list[str]:
    errors = []
    try:
        tree = ast.parse(code, filename=filepath)
    except SyntaxError as e:
        errors.append(f"Error de sintaxis en {filepath}: {e}")
        return errors

    normalized_path = filepath.replace("\\", "/")
    
    errors.extend(_check_forbidden_constructs(tree, normalized_path, contract))
    errors.extend(_check_exports(tree, normalized_path, contract))
    errors.extend(_check_tests(tree, normalized_path, contract))
    errors.extend(_check_imports(tree, normalized_path, contract))
    errors.extend(_check_patterns(tree, normalized_path, contract))
    errors.extend(_check_calls(tree, normalized_path, contract))
    errors.extend(_check_structures(tree, normalized_path, contract))
    
    return errors

def run_mypy(filepaths: list[str]) -> tuple[bool, str]:
    logging.info(f"Ejecutando MyPy en modo estricto para {len(filepaths)} archivos...")
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--strict",
                *filepaths,
            ],
            capture_output=True,
            text=True,
            timeout=600
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        error_message = f"Fallo de infraestructura al ejecutar MyPy: {e}. Asegúrate de que MyPy está instalado y el entorno es correcto."
        logging.error(error_message)
        return False, error_message

def validate_design(design: dict, contract: AcceptanceContract) -> tuple[bool, list[str]]:
    errors: list[str] = []
    
    # 1. Contract validation against design plan
    actions = design.get("actions", [])
    created_files = {a["filepath"].replace("\\", "/") for a in actions if a.get("operation", "").upper() == "CREATE"}
    modified_files = {a["filepath"].replace("\\", "/") for a in actions if a.get("operation", "").upper() == "MODIFY"}
    deleted_files = {a["filepath"].replace("\\", "/") for a in actions if a.get("operation", "").upper() == "DELETE"}
    all_action_files = created_files | modified_files | deleted_files

    missing_creations = contract.required_new_files - created_files
    if missing_creations:
        errors.append(f"El diseño no crea archivos requeridos por el contrato: {sorted(missing_creations)}")

    missing_modifications = contract.required_modified_files - modified_files
    if missing_modifications:
        errors.append(f"El diseño no modifica archivos requeridos por el contrato: {sorted(missing_modifications)}")

    missing_deletions = contract.required_deleted_files - deleted_files
    if missing_deletions:
        errors.append(f"El diseño no elimina archivos requeridos por el contrato: {sorted(missing_deletions)}")

    touched_preserved = contract.preserved_files & all_action_files
    if touched_preserved:
        errors.append(f"El diseño modifica o elimina archivos que deben ser preservados: {sorted(touched_preserved)}")
    
    # 2. Path, operation, and filesystem state validation
    filepaths_to_op: dict[str, str] = {}
    allowed_ops = {"CREATE", "MODIFY", "DELETE"}
    allowed_types = {"production", "test", "config", "none"}

    # Check dependencies for safe paths
    for dependency in design.get("dependencies", []):
        try:
            resolve_safe_path(".", dependency)
        except ValueError as e:
            errors.append(f"Ruta de dependencia inválida: {e}")

    for action in design.get("actions", []):
        path = action["filepath"]
        op = action.get("operation", "").upper()

        try:
            safe_path = resolve_safe_path(".", path)
        except ValueError as e:
            errors.append(f"Ruta de acción inválida: {e}")
            continue

        if op not in allowed_ops:
            errors.append(f"Operación inválida '{op}' para {path}. Permitidas: {allowed_ops}")
        if action.get("file_type") not in allowed_types:
            errors.append(f"Tipo de archivo inválido '{action.get('file_type')}' para {path}. Permitidos: {allowed_types}")

        if path in filepaths_to_op:
            errors.append(f"Acción duplicada/conflictiva para la ruta: {path}")
        filepaths_to_op[path] = op

        path_exists = os.path.exists(safe_path)
        if op == "CREATE" and path_exists:
            errors.append(f"Conflicto: CREATE sobre un archivo que ya existe: {path}")
        if op == "MODIFY" and not path_exists:
            errors.append(f"Conflicto: MODIFY sobre un archivo que no existe: {path}")
    
    return not errors, errors

def validate_generated_manifest(generated_files: dict[str, str], contract: AcceptanceContract) -> tuple[bool, str]:
    required_changed_files = contract.required_new_files | contract.required_modified_files

    generated = {p.replace("\\", "/") for p in generated_files.keys()}
    missing = required_changed_files - generated

    if missing:
        return False, f"Faltan archivos que debían ser creados o modificados según el contrato: {sorted(missing)}"

    return True, ""

def validate_final_state(contract: AcceptanceContract) -> tuple[bool, str]:
    """
    Checks that all files required to exist at the end are present in the filesystem.
    """
    errors = []
    for path in contract.required_final_files:
        try:
            safe_path = resolve_safe_path(".", path)
            if not os.path.exists(safe_path):
                errors.append(f"El archivo final requerido '{path}' no existe en el sistema de archivos.")
        except ValueError as e:
            errors.append(str(e))
    
    if errors:
        return False, "\n".join(errors)
    
    return True, ""

def resolve_safe_path(root: str, relative_path: str) -> str:
    root_abs = os.path.abspath(root)
    target_abs = os.path.abspath(os.path.join(root_abs, relative_path))

    if os.path.commonpath([root_abs, target_abs]) != root_abs:
        raise ValueError(f"Ruta fuera del repositorio: {relative_path}")

    return target_abs

# =====================================================================
# FASES DEL PIPELINE DE ARQUITECTURA EVOLUTIVA
# =====================================================================
def fetch_issue(issue_id: int) -> tuple[str, str]:
    logging.info(f"Leyendo requisitos en el Issue #{issue_id}...")
    issue = repo.get_issue(number=issue_id)
    return issue.title, issue.body

def agent_analyze_and_design(title: str, description: str, contract: AcceptanceContract, repo_context: RepositoryContext, design_feedback: str = "") -> dict:
    source_index_json = json.dumps({fp: summary.model_dump(exclude={'file_hash', 'estimated_tokens', 'referenced_symbols'}) for fp, summary in repo_context.source_index.items()}, indent=2)
    test_index_json = json.dumps({fp: summary.model_dump(exclude={'file_hash', 'estimated_tokens', 'referenced_symbols'}) for fp, summary in repo_context.test_index.items()}, indent=2)
    arch_conflicts_json = json.dumps([c.model_dump() for c in repo_context.architecture_conflicts], indent=2)
    contract_json = contract.model_dump_json(indent=2, exclude={'required_calls', 'required_patterns', 'required_structures', 'required_imports', 'forbidden_imports', 'required_decorators'})

    relevant_files_context = ""
    if repo_context.relevant_source_files or repo_context.relevant_test_files:
        relevant_files_context += "\n\nCONTENIDO DE ARCHIVOS RELEVANTES (PRE-SELECCIONADOS POR RELEVANCIA):\n"
        for path, content in repo_context.relevant_source_files.items():
            relevant_files_context += f"--- INICIO {path} ---\n{content}\n--- FIN {path} ---\n"
        for path, content in repo_context.relevant_test_files.items():
            relevant_files_context += f"--- INICIO {path} ---\n{content}\n--- FIN {path} ---\n"

    prompt = f"""
    Actúas como el Arquitecto de Software Principal. Tu objetivo es diseñar una solución técnica estructurada, elegante, testable y lista para producción que cumpla con la especificación del Issue.

    Para entender el sistema, tienes varias fuentes de información clave:
    1. CONTRATO DE ACEPTACIÓN: Las reglas estrictas y deterministas que tu diseño DEBE cumplir. Es tu principal restricción.
    2. DOCUMENTO DE ARQUITECTURA: Describe la visión y restricciones del sistema (el 'porqué'). ¡CUIDADO! Puede estar desactualizado.
    3. CONFLICTOS DE ARQUITECTURA: Un análisis automático ha detectado posibles desactualizaciones en el documento de arquitectura.
    4. ÍNDICES AST: Un análisis profundo y fiable de cada archivo Python (el 'cómo' detallado). Esta es tu fuente de verdad sobre el estado actual del código.
    5. CONTENIDO DE ARCHIVOS RELEVANTES: El contenido completo de los archivos más importantes para esta tarea.

    CONTRATO DE ACEPTACIÓN (REGLAS OBLIGATORIAS PARA TU DISEÑO):
    --- INICIO CONTRATO ---
    {contract_json}
    --- FIN CONTRATO ---

    CONFLICTOS DETECTADOS ENTRE ARQUITECTURA Y CÓDIGO REAL:
    --- INICIO CONFLICTOS ---
    {arch_conflicts_json if repo_context.architecture_conflicts else "[No se detectaron conflictos. Se asume que la documentación está actualizada.]"}
    --- FIN CONFLICTOS ---

    ÍNDICE DE CÓDIGO FUENTE (SÍMBOLOS, IMPORTS, ETC.):
    --- INICIO ÍNDICE FUENTE ---
    {source_index_json}
    --- FIN ÍNDICE FUENTE ---

    ÍNDICE DE PRUEBAS (SÍMBOLOS, IMPORTS, ETC.):
    --- INICIO ÍNDICE PRUEBAS ---
    {test_index_json}
    --- FIN ÍNDICE PRUEBAS ---

    DOCUMENTO DE ARQUITECTURA:
    --- INICIO DOCUMENTO ---
    {repo_context.architecture_document if repo_context.architecture_document else "[No se encontró documento de arquitectura. Basa tus decisiones en el mapa del repositorio y los principios de Clean Architecture.]"}
    --- FIN DOCUMENTO ---

    {relevant_files_context}

    🛠️ 1. REGLAS DE RECONCILIACIÓN Y TOPOLOGÍA (TU CONTRATO PRINCIPAL):
    - ALINEACIÓN ESTRICTA: Reconcilia los requerimientos funcionales con la 'TOPOLOGÍA EN DISCO ACTUAL'. Utiliza obligatoriamente las clases y métodos existentes.
    - INSPECCIÓN DE FIRMAS OBLIGATORIA: Examina meticulosamente el mapa (AST) adjunto para ver si el método '__init__' de las clases objetivo declara parámetros. Queda terminantemente PROHIBIDO pasar parámetros con nombre (kwargs) si la estructura no coincide con la firma real dictada por el mapa.

    🏗️ 2. PRINCIPIOS DE ARQUITECTURA Y DISEÑO (CLEAN CODE):
    - PROTECCIÓN ESTÁTICA EXTREMA (VULTURE): Para todo archivo de producción nuevo, exige obligatoriamente la declaración explícita de '__all__ = ["NombreClase", "nombre_funcion"]' al inicio del archivo. Esto certifica al linter que son interfaces públicas blindadas.

    ESPECIFICACIÓN FUNCIONAL DEL ISSUE:
    - Título: {title}
    - Requisitos: {description}

    {f"FEEDBACK DEL DISEÑO ANTERIOR (DEBES CORREGIR ESTO):\\n{design_feedback}" if design_feedback else ""}

    TOPOLOGÍA EN DISCO ACTUAL Y FIRMAS AST:
    --- INICIO MAPA ---
    {repo_context.repository_map if repo_context.repository_map else "[Repositorio limpio]"}
    --- FIN MAPA ---
    """
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ProjectDesign,
        temperature=0.1
    )
    response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
    return json.loads(response.text)

def agent_implement_code(action: dict, file_contract: FileContract, design: dict, generated_so_far: dict[str, str], feedback: str = "") -> str:
    logging.info(f"Procesando '{action['filepath']}' | Operacion: {action['operation']} con {MODEL_LIGHT}...")
    contexto_acumulado = "".join([f"\n\n# Archivo: '{path}'\n{code}\n" for path, code in generated_so_far.items()])
    contexto_dependencias = "".join([f"\n\n# Codigo de referencia ('{dep}'):\n{context_manager.get_file_content(dep)}\n" for dep in design.get("dependencies", [])])
    feedback_prompt = f"\n\n[ALERT] REPORTE DE FALLOS O RECHAZOS DE LINTER EN ESTE ARCHIVO:\n{feedback}" if feedback else ""
    file_contract_json = file_contract.model_dump_json(indent=2)

    # --- INYECCIÓN DE CÓDIGO EXISTENTE PARA OPERACIONES DE MODIFICACIÓN ---
    existing_code_context = ""
    if action['operation'].upper() == 'MODIFY':
        existing_code = context_manager.get_file_content(action['filepath'])
        existing_code_context = f"\n\nCÓDIGO ACTUAL DEL ARCHIVO (PARA MODIFICAR):\n{MD_FENCE}python\n{existing_code}\n{MD_FENCE}\n"

    prompt = f"""
    Implementa o refactoriza el contenido del archivo: '{action['filepath']}'.
    {existing_code_context}
    ESPECIFICACIONES TECNICAS DEL ARQUITECTO:
    - Firmas y estructuras esperadas: {action['signatures']}
    - Instrucciones precisas de codificacion: {action['instructions']}
    
    📜 CONTRATO DE ARCHIVO (REGLAS OBLIGATORIAS PARA ESTE ARCHIVO):
    {file_contract_json}
    {contexto_acumulado}{contexto_dependencias}{feedback_prompt}

    Debes cumplir ESTRICTAMENTE con todas las reglas del CONTRATO DE ARCHIVO. Las instrucciones del arquitecto son una guía, pero el contrato es la ley.
    Devuelve UNICAMENTE el codigo limpio dentro de un bloque markdown usando {MD_FENCE}. No añadas texto explicativo fuera del bloque.
    """
    response = ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
    ext = action['filepath'].split('.')[-1]
    return extract_code(response.text, ext if ext in ["python", "json", "ini", "yaml"] else "python")

def agent_generate_tests(action: dict, production_code_context: str, issue_desc: str, feedback: str = "") -> str:
    logging.info(f"Disenando suite de pruebas unitarias para '{action['filepath']}'...")

    existing_test_code = ""
    if action["operation"].upper() == "MODIFY":
        existing_test_code = context_manager.get_file_content(action["filepath"])

    prompt = f"""
    Escribe una suite de pruebas unitarias exhaustiva con 'pytest' para validar el archivo: '{action['filepath']}'

    REQUISITOS ORIGINALES DEL ISSUE (FUENTE DE VERDAD SUPERIOR):
    {issue_desc}

    FIRMAS PROPUESTAS POR EL ARQUITECTO:
    {action["signatures"]}

    INSTRUCCIONES ESPECÍFICAS DEL ARCHIVO:
    {action["instructions"]}

    Las instrucciones del arquitecto están subordinadas al Issue original.
    Si existe una contradicción, prevalece el Issue.

    CONTEXTO DEL CODIGO DE PRODUCCION SISTEMICO:
    {production_code_context}

    📜 ESTÁNDARES DE DISEÑO DE TESTING INDUSTRIAL:
    1. INDEPENDENCIA Y AISLAMIENTO: Usa 'unittest.mock.patch' para aislar dependencias externas o de I/O.
    2. TIPADO ESTRICTO OBLIGATORIO: Todas las funciones de test y los argumentos (incluyendo los mocks inyectados por `@patch`) deben tener type hints (ej. `def test_algo(mock_obj: Mock) -> None:`).
    4. TESTEO EXHAUSTIVO DE INTERFACES PÚBLICAS: Es obligatorio importar, instanciar y usar explícitamente todas las clases o funciones declaradas en la variable '__all__' del archivo de producción objetivo para reducir la tasa de código muerto de Vulture a 0%.

    {'FEEDBACK DEL INTENTO ANTERIOR (DEBES CORREGIR ESTO):' + feedback if feedback else ''}

    {f'''
    CÓDIGO DE TEST EXISTENTE (OPERACIÓN MODIFY):
    El siguiente código ya existe en el archivo. Debes preservarlo, corregirlo si el feedback lo indica, y añadir nuevas pruebas para los nuevos requisitos. No elimines pruebas existentes que no estén relacionadas con el feedback.
    ---
    {existing_test_code}
    ---
    ''' if existing_test_code else ''}

    Devuelve UNICAMENTE el codigo de pytest en un bloque markdown usando {MD_FENCE}python.
    """
    response = ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
    return extract_code(response.text, "python")

def run_local_tests(test_filename: str) -> tuple[bool, str]:
    logging.info(f"Ejecutando pytest para {test_filename}...")
    try:
        result = subprocess.run([sys.executable, "-m", "pytest", "-v", test_filename], capture_output=True, text=True, timeout=600)
        return result.returncode == 0, result.stdout + "\n" + result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        error_message = f"Fallo de infraestructura al ejecutar Pytest: {e}. Asegúrate de que Pytest está instalado y el entorno es correcto."
        logging.error(error_message)
        return False, error_message

def agent_security_audit(generated_files: dict[str, str]) -> SecurityAuditResult:
    logging.info(f"Realizando auditoria de robustez del ecosistema modular con {MODEL_HEAVY}...")
    contexto_auditoria = "".join([f"\n\nArchivo: '{path}'\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n" for path, code in generated_files.items()])
        
    prompt = f"""
    Analiza la calidad de diseno, desacoplamiento, programacion defensiva y control de excepciones del siguiente lote transaccional de archivos:
    {contexto_auditoria}

    Escribe un dictamen de robustez industrial. Responde con un JSON que se ajuste al esquema `SecurityAuditResult`.
    Si el código es seguro para producción, `approved` será `true`.
    Si la modularidad presenta fallos críticos, imports circulares o vulnerabilidades, `approved` será `false` y `findings` contendrá una lista de los problemas encontrados.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SecurityAuditResult,
        temperature=0.0,
    )
    try:
        response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
        result = SecurityAuditResult.model_validate_json(response.text)
        return result
    except (json.JSONDecodeError, ValidationError, Exception) as e:
        logging.error(f"Fallo en la API de auditoria o en la validación de su respuesta: {e}")
        return SecurityAuditResult(approved=False, findings=[f"Fallo en la ejecución de la API de auditoria: {e}"])

# =====================================================================
# AGENTES DE DOCUMENTACION DINAMICA (DOCS-AS-CODE)
# =====================================================================
def agent_generate_execution_report(design: dict, generated_files: dict[str, str], pytest_log: str, sast_report: str, issue_id: int, title: str) -> str:
    logging.info(f"Compilando reporte de ejecucion para Issue #{issue_id}...")
    contexto_archivos = "".join([f"\n\n### Archivo: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n" for path, code in generated_files.items()])
    prompt = f"""
    Eres un documentador tecnico senior. Escribe un reporte de ingenieria de software en Markdown detallando los resultados de la tarea:
    Issue #{issue_id}: '{title}'

    DATOS DE LA EJECUCION:
    - Justificacion de Arquitectura: {design['architecture_justification']}
    - Cambios realizados: {contexto_archivos}
    - Pruebas locales: {MD_FENCE}\n{pytest_log}\n{MD_FENCE}
    - Auditoria de robustez: {MD_FENCE}\n{sast_report}\n{MD_FENCE}

    Devuelve UNICAMENTE el codigo Markdown.
    """
    response = ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt)
    os.makedirs("docs/reports", exist_ok=True)
    report_path = f"docs/reports/run_issue_{issue_id}.md"
    with open(report_path, "w", encoding="utf-8") as f: f.write(response.text.strip())
    logging.info(f"Reporte guardado en '{report_path}'")
    return report_path

def agent_update_architecture_doc(design: dict, repo_map: str) -> str:
    logging.info("Sincronizando evolucion del manual de arquitectura...")
    arch_file = "docs/ARCHITECTURE.md"
    existing_content = open(arch_file, "r", encoding="utf-8").read() if os.path.exists(arch_file) else "[Crear desde cero]"
    prompt = f"""
    Eres el Arquitecto de Soluciones de Olivia. Actualiza 'docs/ARCHITECTURE.md'.
    Refactorizaciones: {design['architecture_justification']}
    NUEVA TOPOLOGIA EN DISCO: {MD_FENCE}\n{repo_map}\n{MD_FENCE}
    PREVIO: {existing_content}
    
    Devuelve UNICAMENTE el Markdown definitivo.
    """
    response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt)
    os.makedirs("docs", exist_ok=True)
    with open(arch_file, "w", encoding="utf-8") as f: f.write(response.text.strip())
    return arch_file

def agent_update_user_manual(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str]) -> str:
    logging.info(f"Evaluando impacto operativo del Issue #{issue_id} en el Manual de Usuario...")
    manual_path = "docs/USER_MANUAL.md"
    existing_content = open(manual_path, "r", encoding="utf-8").read() if os.path.exists(manual_path) else "[Vacio]"
    contexto_cambios = "".join([f"\nArchivo modificado: {p}\n" for p in generated_files.keys()])

    prompt = f"""
    Actúas como un Redactor Técnico Senior. Actualiza el manual de usuario ('docs/USER_MANUAL.md') de forma incremental.
    - Tarea: Issue #{issue_id} - '{title}' | Descripción: {description} | Archivos: {contexto_cambios}
    ESTADO ACTUAL: {existing_content}

    Evalúa si afecta la UX. Si es técnico interno, devuelve el manual intacto. Si impacta, traduce la mejora a operativas sin usar jerga de código.
    Devuelve UNICAMENTE el Markdown definitivo.
    """
    response = ai_client.models.generate_content(
        model=MODEL_HEAVY, contents=prompt,
        config=types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_budget=1024), temperature=0.2)
    )
    clean_text = response.text.strip()
    if clean_text.startswith(f"{MD_FENCE}markdown"): clean_text = clean_text[11:]
    if clean_text.endswith(MD_FENCE): clean_text = clean_text[:-3]
    os.makedirs("docs", exist_ok=True)
    with open(manual_path, "w", encoding="utf-8") as f: f.write(clean_text.strip())
    return manual_path

# =====================================================================
# AGENTE CLÍNICO DE DIAGNÓSTICO DE FALLOS CON GOBERNANZA AUTOMATIZADA
# =====================================================================
def agent_analyze_pipeline_failure(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], gate_results: list[GateResult]) -> str:
    logging.warning("El ciclo colapsó. Invocando Diagnóstico Clínico de IA...")
    contexto_archivos = "".join([f"\n### Archivo: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n" for path, code in generated_files.items()])
    gate_report = "\n".join([f"- Gate: {g.name}, Executed: {g.executed}, Passed: {g.passed}\nOutput:\n{g.output}" for g in gate_results])

    prompt = f"""
    Actúas como un Ingeniero Principal de DevOps y Experto en Diagnóstico de Agentes. El pipeline falló tras agotar los reintentos de calidad.
    Realiza una autopsia técnica y emite un reporte Markdown detallado sobre qué causó el bloqueo.
    
    Contexto: Issue #{issue_id}: '{title}' | Spec: {description}
    CÓDIGO GENERADO: {contexto_archivos}
    
    RESULTADOS DE LOS QUALITY GATES:
    {gate_report}

    Escribe el Reporte Clínico en Markdown con Análisis de Causa Raíz y Recomendación Inmediata al humano.
    Usa únicamente los resultados incluidos en GATE_RESULTS. No atribuyas fallos a una fase con executed=false.
    Distingue explícitamente:
    - FALLO OBSERVADO (basado en un gate con passed=false)
    - RIESGO INFERIDO (tu análisis sobre el código que podría haber causado el fallo)
    - RECOMENDACIÓN PREVENTIVA (sugerencias para el futuro)

    🚨 INSTRUCCIÓN CRÍTICA DE GOBERNANZA AUTOMATIZADA 🚨:
    Si determinas que la causa raíz del fallo NO es un mero despiste tipográfico de sintaxis, sino que el Agente Coder necesita directrices explícitas en los Criterios de Aceptación Técnicos para superar una barrera estricta o trampa de herramientas (ej. inyectar comentarios de bypass como '# vulture: ignore', modificar firmas específicas o mitigar asimetrías de testing), DEBES incluir obligatoriamente la siguiente etiqueta exacta en una línea independiente al final de tu reporte:
    [ACTION: DELEGATE_TO_PO]
    
    Si el error es puramente técnico subsanable sin alterar las especificaciones, omite la etiqueta.
    """
    try:
        response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt)
        logging.error(f"REPORTE DE AUTODIAGNÓSTICO POST-MORTEM:\n{response.text.strip()}")
        return response.text.strip()
    except Exception as e: return f"Error de diagnostico: {e}"

# =====================================================================
# AGENTE DE REVISIÓN DE CÓDIGO (NUEVO)
# =====================================================================
def agent_code_reviewer(design: dict, generated_files: dict[str, str], issue_desc: str) -> CodeReviewResult:
    """
    Un agente que actúa como un revisor de código senior.
    Valida que el código generado se adhiere semánticamente a las instrucciones.
    """
    logging.info(f"Realizando revisión de código semántica con {MODEL_HEAVY}...")
    contexto_codigo = "".join([f"\n\n### Archivo: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n" for path, code in generated_files.items()])
    
    prompt = f"""
    Actúas como un Ingeniero de Software Principal realizando una revisión de código. Tu tarea es verificar que el código generado cumple ESTRICTAMENTE con las instrucciones del arquitecto Y con los requisitos originales del Issue.

    **Requisitos Originales del Issue:**
    {issue_desc}

    **Plan del Arquitecto:**
    {json.dumps(design, indent=2)}

    **Código Generado para Revisión:**
    {contexto_codigo}

    Busca discrepancias lógicas, como manejo incorrecto de excepciones, violación de principios (ej. Fail-Fast), o pruebas que no validan el requisito real.
    
    El criterio Anti-Laziness relativo a la entrega completa de archivos
    ha sido validado determinísticamente mediante manifest_validation.

    No evalúes la presencia de un árbol textual dentro de los archivos
    generados. Evalúa únicamente que el manifiesto contenga todos los
    artefactos obligatorios.

    El Issue original es la fuente de verdad superior.
    Si el plan del arquitecto contradice el Issue:
    1. No exijas al código cumplir la instrucción contradictoria.
    2. Rechaza el diseño.
    3. Identifica la contradicción como DESIGN_CONFLICT en tu mensaje.
    
    Responde con un JSON que se ajuste al esquema `CodeReviewResult`. Si todo es correcto, `approved` será `true`. Si hay fallos, `approved` será `false` y `findings` contendrá una lista de objetos con `filepath` y `message`.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=CodeReviewResult,
        temperature=0.0,
    )
    response = ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
    try:
        cleaned_json = extract_code(response.text, "json")
        result = CodeReviewResult.model_validate_json(cleaned_json)
        return result
    except (json.JSONDecodeError, ValidationError) as e:
        logging.error(f"Error al decodificar la respuesta del Code Reviewer: {e}\nRespuesta recibida: {response.text}")
        return CodeReviewResult(approved=False, findings=[ReviewFinding(filepath="all", message=f"Fallo de formato en la respuesta del Code Reviewer: {response.text}")])

# =====================================================================
# GIT FLOW DE ALTA TRAZABILIDAD CON RUN ID
# =====================================================================
def deploy_to_github(design: dict, generated_files: dict[str, str], report_path: str, arch_path: str, user_manual_path: str, issue_id: int, run_id: str) -> None:
    print("\n[DEVOPS] Inicializando PR de alta trazabilidad...")
    commit_title = f"feat(issue-{issue_id}): [{run_id}] refactorizacion y solucion modular evolutiva"
    commit_body = f"Trazabilidad: {run_id}\nJustificacion: {design['architecture_justification']}"
    
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

        fresh_repo = Github(auth=Auth.Token(os.getenv("GITHUB_TOKEN")), timeout=60).get_repo(repo_path)
        pr = fresh_repo.create_pull(title=f"[Agente SDLC] [{run_id}] Issue #{issue_id}", body=f"Cambio autónomo (Run {run_id}).\nCloses #{issue_id}", head=branch_name, base="main")

        logging.info(f"Pull Request creado: {pr.html_url}")
        logging.info(f"Para probar localmente, ejecuta: git fetch origin && git checkout {branch_name}")

        try:
            issue = fresh_repo.get_issue(number=issue_id)
            for lbl in ["status:in-progress", "ai:ready-to-code"]:
                if lbl in [l.name for l in issue.labels]: issue.remove_from_labels(lbl)
            try: fresh_repo.get_label("status:pending-review")
            except: fresh_repo.create_label("status:pending-review", "d4c5f9")
            issue.add_to_labels("status:pending-review")
        except Exception: pass
    except Exception as exc:
        logging.exception("Error crítico durante el despliegue.")
        raise
    finally:
        logging.info("Limpiando entorno y volviendo a la rama principal...")
        subprocess.run(["git", "fetch", "origin"], capture_output=True, timeout=300)
        subprocess.run(["git", "checkout", "main"], capture_output=True, timeout=60)

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

def materialize_cached_files(generated_files: dict[str, str], feedback_dict: dict[str, str]) -> None:
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
# =====================================================================
# COORDINADOR DEL WORKFLOW CENTRAL UNIFICADO
# =====================================================================
def run_pipeline(issue_id: int, run_id: str, run_log_dir: str) -> None:
    try:
        issue_to_update = repo.get_issue(number=issue_id)
        if "ai:ready-to-code" in [l.name for l in issue_to_update.labels]: 
            issue_to_update.remove_from_labels("ai:ready-to-code")
        try: 
            repo.get_label("status:in-progress")
        except: 
            repo.create_label("status:in-progress", "fef2c0")
        issue_to_update.add_to_labels("status:in-progress")
    except: 
        pass

    title, desc = fetch_issue(issue_id)
    logging.info(f"Pipeline iniciado - Issue #{issue_id}: '{title}'")
    
    context_budget = ContextBudget()
    repo_context = context_manager.build_repository_context(desc, context_budget)
    logging.info(f"Contexto del repositorio construido. {len(repo_context.source_index)} archivos fuente y {len(repo_context.test_index)} archivos de test indexados.")
    logging.info(f"Seleccionados {len(repo_context.relevant_source_files)} archivos fuente y {len(repo_context.relevant_test_files)} de test como contexto relevante.")
    if repo_context.architecture_conflicts:
        logging.warning(f"Se detectaron {len(repo_context.architecture_conflicts)} conflictos entre la arquitectura y el código real.")
    
    # Generate the acceptance contract from the issue description
    canonical_contract = agent_generate_acceptance_contract(title, desc, repo_context)
    logging.info(f"Contrato Canónico generado: {canonical_contract.model_dump_json(indent=2)}")
    canonical_contract: AcceptanceContract # Declare it here to be accessible outside the loop
    
    # --- PHASE 1: Contract Generation and Validation (Critical, Fail-Fast) ---
    # These gates run only once per pipeline execution, not per attempt.
    initial_gates: list[GateResult] = []
    try:
        canonical_contract = agent_generate_acceptance_contract(title, desc, repo_context)
        logging.info(f"Contrato Canónico generado: {canonical_contract.model_dump_json(indent=2)}")
        initial_gates.append(GateResult(attempt=1, name="contract_generation", executed=True, passed=True, output="Contrato generado con éxito."))
    except ContractGenerationError as e:
        logging.error(f"Fallo crítico al generar el contrato de aceptación: {e}")
        initial_gates.append(GateResult(attempt=1, name="contract_generation", executed=True, passed=False, output=str(e)))
        # This is a pipeline-stopping error, so we'll log it and exit the attempt loop.
        # The outer try-except in __main__ will catch it and handle the overall pipeline failure.
        raise # Re-raise to stop the current pipeline run.

    contract_capabilities_valid, contract_capabilities_errors = validate_contract_capabilities(canonical_contract, _validator_registry)
    initial_gates.append(GateResult(attempt=1, name="contract_capabilities_validation", executed=True, passed=contract_capabilities_valid, output="\n".join(contract_capabilities_errors)))
    if not contract_capabilities_valid:
        logging.error(f"El contrato contiene reglas no soportadas por el orquestador: {contract_capabilities_errors}")
        raise ContractGenerationError("Contrato generado con reglas no soportadas.") # Re-use the same error type

    # --- PHASE 2: Iterative Development Attempts ---
    
    attempt, max_attempts, pipeline_passed = 1, 3, False
    generated_files, feedback_dict = {}, {}
    design, design_feedback = None, ""
    all_attempt_results: list[list[GateResult]] = []
    all_attempt_results.append(initial_gates) # Add initial gates to results

    while attempt <= max_attempts and not pipeline_passed:
        current_attempt_gates: list[GateResult] = []

        # --- AISLAMIENTO DE INTENTOS: Restaurar el workspace a un estado limpio ---
        logging.info(f"Preparando intento {attempt}/{max_attempts}. Restaurando workspace a estado base...")
        subprocess.run(["git", "reset", "--hard"], check=True, capture_output=True, timeout=120)
        subprocess.run(["git", "clean", "-fd"], check=True, capture_output=True, timeout=120)
        materialize_cached_files(generated_files, feedback_dict)

        logging.info(f"Ejecutando ciclo de desarrollo (Intento {attempt}/{max_attempts})...")

        if design is None: # Diseñar solo si no existe un plan previo
            logging.info("Diseñando plan estructural base o rediseñando tras rechazo...")
            design = agent_analyze_and_design(title, desc, canonical_contract, repo_context, design_feedback)
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
                code = agent_implement_code(act, file_contract, design, generated_files, current_feedback)
            else: 
                production_code_context = "\n\n".join([f"# Archivo: {p}\n{c}" for p, c in generated_files.items() if not p.startswith("tests/")])
                code = agent_generate_tests(act, production_code_context, desc, current_feedback)
            
            # GATES: Calidad de código y AST contractual
            is_valid, quality_report = validate_code_quality(code, path)
            contract_errors = validate_contractual_ast(code, path, canonical_contract)
            
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
        manifest_valid, manifest_error = validate_generated_manifest(generated_files, canonical_contract)
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

        # GATE: MyPy (excluding whitelist)
        files_for_mypy = [p for p in generated_files.keys() if p.endswith(".py") and "vulture_whitelist.py" not in p]
        mypy_passed, mypy_log = run_mypy(files_for_mypy)
        current_attempt_gates.append(GateResult(attempt=attempt, name="mypy", executed=True, passed=mypy_passed, output=mypy_log))
        if not mypy_passed:
            logging.warning(f"MyPy encontró errores:\n{mypy_log}")
            feedback_dict = parse_compiler_output(mypy_log)
            all_attempt_results.append(current_attempt_gates)
            attempt += 1
            continue

        # GATE: Pytest (específico y regresión)
        pytest_passed, pytest_log = True, ""
        for act in test_actions:
            path = act['filepath']
            success, log = run_local_tests(resolve_safe_path(".", path))
            pytest_log += f"\n--- {path} ---\n{log}"
            if not success:
                pytest_passed = False
                feedback_dict[path] = log
        
        if pytest_passed:
            logging.info("Ejecutando suite de regresión completa de pytest...")
            regression_result = subprocess.run([sys.executable, "-m", "pytest", "-v"], capture_output=True, text=True, timeout=600)
            pytest_passed = regression_result.returncode == 0
            regression_log = regression_result.stdout + regression_result.stderr
            pytest_log += f"\n--- REGRESIÓN COMPLETA ---\n{regression_log}"

        current_attempt_gates.append(GateResult(attempt=attempt, name="pytest", executed=True, passed=pytest_passed, output=pytest_log))
        if not pytest_passed:
            logging.warning(f"Pruebas unitarias fallaron. Realimentando sistema...\n{pytest_log}")
            all_attempt_results.append(current_attempt_gates)
            attempt += 1
            continue

        # GATE: Ruff/Vulture
        static_passed, static_log = run_static_analysis(list(generated_files.keys()))
        reload_code_after_ruff(generated_files) # Recargar por si --fix modificó algo
        current_attempt_gates.append(GateResult(attempt=attempt, name="static_analysis", executed=True, passed=static_passed, output=static_log))
        if not static_passed:
            logging.warning(f"Análisis estático falló:\n{static_log}")
            feedback_dict = {"all": static_log}
            all_attempt_results.append(current_attempt_gates)
            attempt += 1
            continue

        # GATE: Code Reviewer
        review_result = agent_code_reviewer(design, generated_files, desc)
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

        # GATE: Auditoría final
        audit_result = agent_security_audit(generated_files)
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
        
        pm_report = agent_analyze_pipeline_failure(issue_id, title, desc, design or {}, generated_files, [g for attempt_gates in all_attempt_results for g in attempt_gates])
        
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
                issue = repo.get_issue(number=issue_id)
                if "status:in-progress" in [l.name for l in issue.labels]: 
                    issue.remove_from_labels("status:in-progress")
                try: 
                    repo.get_label("po:human-validation-required")
                except: 
                    repo.create_label("po:human-validation-required", "fbca04")
                issue.add_to_labels("po:human-validation-required")
                logging.info(f"El PO Agent ha renegociado el Issue #{issue_id}. A la espera de firma en GitHub.")
            except Exception as e: 
                logging.error(f"Fallo al delegar al PO Agent: {e}")
        else:
            try:
                issue = repo.get_issue(number=issue_id)
                if "status:in-progress" in [l.name for l in issue.labels]:
                    issue.remove_from_labels("status:in-progress")
                try:
                    repo.get_label("status:failed")
                except Exception:
                    repo.create_label("status:failed", "d93f0b") # Red
                issue.add_to_labels("status:failed")
                issue.create_comment("Pipeline execution failed due to technical errors. See orchestrator logs for the Post-Mortem report.")
            except Exception as e:
                logging.error(f"Could not update GitHub issue status to 'failed': {e}")
            write_local_log(issue_id, title, False, error_msg, run_log_dir)
        return
        
    final_gates = all_attempt_results[-1]
    report = agent_generate_execution_report(design, generated_files, "\n".join([g.output for g in final_gates if g.name=='pytest']), "\n".join([g.output for g in final_gates if g.name=='security_audit']), issue_id, title)
    arch = agent_update_architecture_doc(design, context_manager.generate_repository_map())
    man = agent_update_user_manual(issue_id, title, desc, design, generated_files)
    
    try:
        deploy_to_github(design, generated_files, report, arch, man, issue_id, run_id)
        write_local_log(issue_id, title, True, "Despliegue y PR completado.", run_log_dir)
    except Exception as e: 
        write_local_log(issue_id, title, False, f"Fallo Git: {e}", run_log_dir)

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
        
        # 3. Run pipeline inside the worktree
        run_pipeline(args.issue, run_id, run_log_dir)

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