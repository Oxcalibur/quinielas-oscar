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
MD_FENCE = "`" * 3

# =====================================================================
# CONFIGURACIÓN DEL LOGGER
# =====================================================================
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] - %(message)s')

# =====================================================================
# FUNCIONES AUXILIARES PURAS (no requieren credenciales ni red)
# =====================================================================
def serialize_ast_signature(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    """Serializa la firma completa de un nodo (clase o función) utilizando ast.unparse."""
    if isinstance(node, ast.ClassDef):
        bases = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except Exception:
                pass
        base_str = f"({', '.join(bases)})" if bases else ""
        return f"class {node.name}{base_str}"
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        keyword = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        try:
            args_str = ast.unparse(node.args)
        except Exception:
            args_str = ""
        returns_str = ""
        if node.returns:
            try:
                returns_str = f" -> {ast.unparse(node.returns)}"
            except Exception:
                pass
        return f"{keyword} {node.name}({args_str}){returns_str}"
    return ""

def extract_ast_signatures(tree: ast.AST) -> dict[str, str]:
    """Extracts top-level classes, their methods, and top-level functions."""
    signatures = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            signatures[node.name] = serialize_ast_signature(node)
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    signatures[f"{node.name}.{child.name}"] = serialize_ast_signature(child)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            signatures[node.name] = serialize_ast_signature(node)
    return signatures



from github import Auth, Github
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError
from typing import Literal, Any

@dataclass
class RuntimeClients:
    ai_client: genai.Client
    github_client: Github
    repo: Any  # github.Repository.Repository

def build_runtime_clients() -> RuntimeClients:
    """Carga credenciales, aplica parches de red y construye los clientes de runtime.

    Llamar esta función es el único mecanismo que activa efectos laterales de red.
    ``import orchestrator`` debe ser siempre seguro y no requerir credenciales.
    """
    import truststore
    try:
        truststore.inject_into_ssl()
    except AttributeError:
        import urllib3
        truststore.inject_into_urllib3()
        
    load_dotenv()

    # Parche SSL opcional (solo si BYPASS_SSL_VERIFY=true)
    if os.getenv("BYPASS_SSL_VERIFY", "false").lower() == "true":
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        import requests as _req
        _original_request = _req.Session.request

        def _patched_request(self, method, url, *args, **kwargs):
            kwargs["verify"] = False
            return _original_request(self, method, url, *args, **kwargs)

        _req.Session.request = _patched_request
        logging.info("[Seguridad] Modo de compatibilidad activo: Verificacion SSL de GitHub omitida.")

    required_env = ["GITHUB_TOKEN", "REPO_OWNER", "REPO_NAME", "GEMINI_API_KEY"]
    missing = [name for name in required_env if not os.getenv(name)]
    if missing:
        raise PreflightError(
            f"Variables de entorno requeridas ausentes: {missing}. "
            "Configura el archivo .env antes de ejecutar el pipeline."
        )

    ai_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    github_client = Github(
        auth=Auth.Token(os.getenv("GITHUB_TOKEN")),
        timeout=60,
    )
    repo = github_client.get_repo(
        f"{os.getenv('REPO_OWNER')}/{os.getenv('REPO_NAME')}"
    )
    return RuntimeClients(
        ai_client=ai_client,
        github_client=github_client,
        repo=repo,
    )

# --- CONFIGURACION DE MODELOS GEMINI 3 (VIGENCIA 2026) ---
MODEL_HEAVY = "gemini-3.1-pro-preview"   # Razonamiento complejo, refactorizacion estructural y auditorias
MODEL_LIGHT = "gemini-3.5-flash"          # Velocidad extrema para codificacion de piezas, tests y reportes

# =====================================================================
# FUNCIONES AUXILIARES DE ANÁLISIS
# =====================================================================
def is_test_file(filepath: str, content: str = None, project_config: "PythonProjectConfiguration" = None) -> bool:
    """Detecta de forma fiable si un archivo es un test usando heurísticas y configuración de pytest."""
    filepath = filepath.replace("\\", "/")
    filename = os.path.basename(filepath)
    
    if filename == "conftest.py":
        return True
        
    testpaths = ["tests", "test", "testing"]
    python_files = ["test_*.py", "*_test.py"]
    
    if project_config:
        if project_config.pytest_paths:
            testpaths = project_config.pytest_paths
        if project_config.pytest_patterns:
            python_files = project_config.pytest_patterns

    path_parts = filepath.split("/")
    in_test_dir = any(part in testpaths for part in path_parts)
    
    matches_pattern = any(fnmatch.fnmatch(filename, pattern) for pattern in python_files)
    
    if matches_pattern:
        return True
        
    if in_test_dir and filename.endswith(".py"):
        return True
        
    if content:
        if re.search(r"^\s*(?:import\s+(?:pytest|unittest)|from\s+(?:pytest|unittest)\s+import)", content, re.MULTILINE):
            return True
            
    return False

# =====================================================================
# GESTOR DE CONTEXTO HIBRIDO (ANALISIS ESTATICO DE ARCHIVOS CON AST)
# =====================================================================
def extract_imported_modules(tree: ast.AST, module_name: str) -> list[str]:
    """Extrae los modulos reales importados usando AST, resolviendo imports relativos."""
    imported_modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            level = node.level
            module = node.module or ""
            if level > 0:
                parts = module_name.split('.')
                if level <= len(parts):
                    base = ".".join(parts[:-level])
                    if base:
                        resolved_base = f"{base}.{module}" if module else base
                    else:
                        resolved_base = module
                else:
                    resolved_base = module
            else:
                resolved_base = module

            if resolved_base:
                imported_modules.add(resolved_base)
                
            for alias in node.names:
                if resolved_base:
                    imported_modules.add(f"{resolved_base}.{alias.name}")
                else:
                    imported_modules.add(alias.name)
                    
    return list(imported_modules)

def resolve_imported_files(imported_modules: list[str], root_path: str, all_py_files: list[str]) -> list[str]:
    """Resuelve los nombres de modulos a archivos exactos."""
    resolved = set()
    
    # Precompute module to file mapping
    module_to_file = {}
    for f in all_py_files:
        mod = f.replace("\\", "/").replace("/", ".").replace(".py", "")
        if mod.endswith(".__init__"):
            mod = mod[:-9]
        module_to_file[mod] = f
        
    for mod in imported_modules:
        if mod in module_to_file:
            resolved.add(module_to_file[mod])
    return list(resolved)

class RepositoryContextManager:
    def __init__(self, root_path=".", cache_dir=None):
        self.root_path = root_path
        self.ignored_dirs = {
            ".git", "venv", "__pycache__", ".pytest_cache", 
            ".env", "node_modules", "dist", "build"
        }
        if cache_dir is None:
            repo_id = None
            try:
                result = subprocess.run(
                    ["git", "remote", "get-url", "origin"],
                    cwd=self.root_path,
                    capture_output=True,
                    text=True,
                    check=True
                )
                url = result.stdout.strip()
                if "://" in url:
                    parts = url.split("/")
                    owner = parts[-2]
                    repo = parts[-1].replace(".git", "")
                    repo_id = f"{owner}/{repo}"
                elif ":" in url:
                    parts = url.split(":")[-1].split("/")
                    owner = parts[-2]
                    repo = parts[-1].replace(".git", "")
                    repo_id = f"{owner}/{repo}"
            except Exception:
                pass
            
            if not repo_id:
                abs_path = os.path.abspath(self.root_path)
                hash_str = hashlib.md5(abs_path.encode()).hexdigest()[:8]
                repo_name = os.path.basename(abs_path)
                repo_id = f"local_{hash_str}/{repo_name}"
                
            self.cache_dir = os.path.expanduser(f"~/.agent-runs/shared-cache/{repo_id}")
        else:
            self.cache_dir = cache_dir
        self.cache_file = os.path.join(self.cache_dir, "repository_index.json")

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
                    for sig in signatures.values():
                        repo_map.append(f"{file_indent}  ↳ {sig}")
                        
        return "\n".join(repo_map)

    def _extract_signatures(self, filepath: str) -> dict[str, str]:
        """Helper to extract signatures from a file path for the repo map."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content, filename=filepath)
            return extract_ast_signatures(tree)
        except Exception:
            return {}

    def get_file_content(self, relative_filepath) -> str:
        """Carga el contenido real de un archivo especifico del repositorio."""
        try:
            full_path = resolve_safe_path(self.root_path, relative_filepath)
            if not os.path.exists(full_path):
                return f"# El archivo '{relative_filepath}' no existe todavia o se creará nuevo."
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"# Error al leer {relative_filepath}: {e!s}"

    def read_architecture_document(self) -> str:
        """Reads the architecture document if it exists."""
        try:
            path = resolve_safe_path(self.root_path, "docs/ARCHITECTURE.md")
            if not os.path.exists(path):
                logging.info("No se encontró 'docs/ARCHITECTURE.md'. Se procederá sin él.")
                return ""
            with open(path, "r", encoding="utf-8") as file:
                return file.read()
        except (OSError, ValueError) as e:
            logging.warning(f"No se pudo leer el documento de arquitectura: {e}")
            return ""

    def _scan_config_files(self) -> tuple[dict[str, str], dict[str, str]]:
        """Scans for and reads common project configuration files."""
        project_config_files = [
            "pyproject.toml",
            "setup.py",
            "pytest.ini",
            "tox.ini",
            "setup.cfg",
            "mypy.ini",
            "ruff.toml",
            ".ruff.toml",
            "conftest.py",
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
            except (OSError, ValueError):
                pass  # Ignore if file not found or can't be read

        return project_configs, dep_files

    def _extract_project_configuration(self, project_configs: dict[str, str], dep_files: dict[str, str]) -> "PythonProjectConfiguration":
        config = PythonProjectConfiguration()

        # 1. Parse configuration files using modular parsers
        for filename, content in project_configs.items():
            try:
                if filename.endswith(".toml"):
                    parsed = parse_pyproject(content)
                    if parsed.get("python_version"):
                        config.python_version = parsed["python_version"]
                    tools = parsed.get("tools", {})
                    if tools.get("mypy"):
                        config.mypy_enabled = True
                        config.detected_quality_tools.append("mypy")
                        if tools["mypy"].get("strict"):
                            config.mypy_strict = True
                        # Read explicit target files from [tool.mypy] files = [...]
                        raw_files = tools["mypy"].get("files")
                        if raw_files:
                            if isinstance(raw_files, list):
                                config.mypy_targets.extend(raw_files)
                            elif isinstance(raw_files, str):
                                config.mypy_targets.extend(
                                    f.strip() for f in raw_files.split(",") if f.strip()
                                )
                    if tools.get("ruff"):
                        config.ruff_enabled = True
                        config.detected_quality_tools.append("ruff")
                    if tools.get("pytest"):
                        config.detected_quality_tools.append("pytest")
                        pytest_cfg = tools["pytest"]
                        pytest_ini = pytest_cfg.get("ini_options", pytest_cfg)  # support both direct and [tool.pytest.ini_options]
                        if pytest_ini.get("testpaths"):
                            config.pytest_paths = pytest_ini["testpaths"]
                        if pytest_ini.get("python_files"):
                            config.pytest_patterns = pytest_ini["python_files"]
                    if tools.get("vulture"):
                        config.vulture_enabled = True
                        config.detected_quality_tools.append("vulture")
                    for dep in parsed.get("dependencies", []):
                        config.dependencies.append(dep)
                    for dep in parsed.get("dev_dependencies", []):
                        config.dev_dependencies.append(dep)

                elif filename.endswith(".cfg") or filename.endswith(".ini"):
                    deps = parse_setup_cfg(content)
                    config.dependencies.extend(deps)
                    # setup.cfg tool detection via configparser (inline, simple)
                    parser = configparser.ConfigParser()
                    parser.read_string(content)
                    for section in parser.sections():
                        sl = section.lower()
                        if "pytest" in sl:
                            config.detected_quality_tools.append("pytest")
                            if parser.has_option(section, "testpaths"):
                                config.pytest_paths = parser.get(section, "testpaths").split()
                            if parser.has_option(section, "python_files"):
                                config.pytest_patterns = parser.get(section, "python_files").split()
                        elif "mypy" in sl:
                            config.mypy_enabled = True
                            config.detected_quality_tools.append("mypy")
                            if parser.has_option(section, "strict"):
                                config.mypy_strict = parser.get(section, "strict").lower() in ("true", "1", "yes")
                            if parser.has_option(section, "files"):
                                raw = parser.get(section, "files")
                                config.mypy_targets.extend(
                                    f.strip() for f in raw.replace(",", "\n").splitlines() if f.strip()
                                )
                        elif "ruff" in sl:
                            config.ruff_enabled = True
                            config.detected_quality_tools.append("ruff")
                        elif "vulture" in sl:
                            config.vulture_enabled = True
                            config.detected_quality_tools.append("vulture")
                elif filename == "setup.py":
                    setup_info = parse_setup_py(content)
                    if setup_info["python_requires"]:
                        config.python_version = setup_info["python_requires"]
                    config.dependencies.extend(setup_info["install_requires"])
                    for deps in setup_info["extras_require"].values():
                        config.dev_dependencies.extend(deps)
            except Exception as e:
                logging.warning(f"Error parseando config {filename}: {e}")

        # 2. Parse dependency files using modular parsers
        for filename, content in dep_files.items():
            try:
                if filename.endswith(".txt"):
                    deps = parse_requirements(content)
                    if "dev" in filename.lower() or "test" in filename.lower():
                        config.dev_dependencies.extend(deps)
                    else:
                        config.dependencies.extend(deps)
                elif "Pipfile" in filename and not filename.endswith(".lock"):
                    parsed = parse_pipfile(content)
                    config.dependencies.extend(parsed.get("dependencies", []))
                    config.dev_dependencies.extend(parsed.get("dev_dependencies", []))
                elif filename.endswith(".lock") and "poetry" in filename.lower():
                    config.dependencies.extend(parse_poetry_lock(content))
                elif filename.endswith(".toml"):
                    parsed = parse_pyproject(content)
                    config.dependencies.extend(parsed.get("dependencies", []))
                    config.dev_dependencies.extend(parsed.get("dev_dependencies", []))
            except Exception as e:
                logging.warning(f"Error parseando dependencias {filename}: {e}")

        # 3. De-duplicate
        config.dependencies = list(set(config.dependencies))
        config.dev_dependencies = list(set(config.dev_dependencies))
        config.detected_quality_tools = list(set(config.detected_quality_tools))

        unique_targets = []
        for t in config.mypy_targets:
            clean_t = t.strip()
            if clean_t and clean_t not in unique_targets:
                unique_targets.append(clean_t)
        config.mypy_targets = unique_targets

        # 4. Fallback: activate tools found in deps but not yet configured
        all_deps = config.dependencies + config.dev_dependencies
        for tool in ["mypy", "ruff", "pytest", "vulture"]:
            if tool in all_deps and tool not in config.detected_quality_tools:
                config.detected_quality_tools.append(tool)
                if tool == "mypy": config.mypy_enabled = True
                if tool == "ruff": config.ruff_enabled = True
                if tool == "vulture": config.vulture_enabled = True

        return config

    def _analyze_python_file(self, filepath: str, project_config: "PythonProjectConfiguration | None" = None) -> "PythonFileSummary | None":
        """Analyzes a single Python file using AST to build a summary."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            
            tree = ast.parse(content, filename=filepath)
            
            imports, classes, functions, exports = [], [], [], []
            referenced_symbols = set()

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions.append(node.name)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                    referenced_symbols.add(node.id)
                elif isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                   isinstance(node.targets[0], ast.Name) and node.targets[0].id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        exports = [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)]

            docstring = ast.get_docstring(tree)
            relative_path = os.path.relpath(filepath, self.root_path).replace("\\", "/")
            module_name_str = relative_path.replace('/', '.').replace('.py', '')

            return PythonFileSummary(
                filepath=relative_path,
                module_name=module_name_str,
                is_test=is_test_file(relative_path, content, project_config),
                classes=classes,
                functions=functions,
                signatures=extract_ast_signatures(tree),
                imports=extract_imported_modules(tree, module_name_str),
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
        arch_text_lower = context.architecture_document.lower()
        all_paths = list(context.source_index.keys()) + list(context.test_index.keys())
        all_summaries = {**context.source_index, **context.test_index}

        # Heuristic 1: Check for mentioned file paths that don't exist.
        mentioned_paths = re.findall(r'[\w/\\-]+\.py', arch_text_lower)
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
                    repository_evidence=["El archivo no existe en el índice del repositorio."],
                    blocks_execution=True # A documented component that is missing is a critical issue.
                ))

        # Heuristic 2: Check for tool usage contradictions.
        if "pytest-mock" in arch_text_lower and ("prescinde" in arch_text_lower or "prohíbe" in arch_text_lower or "no se usa" in arch_text_lower):
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
                    blocks_execution=True # A direct policy contradiction should block.
                ))
        
        # Heuristic 3: Check for mentioned symbols that don't exist in the code.
        # This finds symbols enclosed in backticks, which is a common markdown convention for code.
        mentioned_symbols = re.findall(r'`([\w_]+)`', context.architecture_document)
        for symbol in set(mentioned_symbols):
            # Ignore very common words that might be in backticks but aren't symbols
            if symbol.lower() in ['true', 'false', 'none', 'self', 'cls', 'x', 'y']:
                continue
            
            found = False
            for summary in all_summaries.values():
                if symbol in summary.classes or symbol in summary.functions:
                    found = True
                    break
            if not found:
                conflicts.append(ArchitectureConflict(
                    type="MISSING_SYMBOL",
                    description=f"El símbolo '{symbol}' mencionado en la arquitectura no se encontró en el código.",
                    architecture_reference=f"Mención de `{symbol}`",
                    repository_evidence=["El símbolo no se encontró en ninguna clase o función del índice AST."],
                    blocks_execution=False # This is a warning, as it could be a doc error or a symbol in a non-python file.
                ))

        context.architecture_conflicts = conflicts

    def _derive_quality_policy(self, context: "RepositoryContext", issue_description: str):
        """Deriva la política de calidad de Python a partir de varias fuentes."""
        policy = PythonQualityPolicy()
        
        # Combinar todas las fuentes de texto para facilitar la búsqueda
        arch_text = context.architecture_document.lower()
        issue_text = issue_description.lower()
        config_text = ""
        for content in context.project_configuration.values():
            config_text += content.lower()

        # 1. mypy_strict
        if "strict = true" in config_text or "mypy --strict" in arch_text or "mypy --strict" in issue_text:
            policy.mypy_strict = True

        # 2. Anotaciones de argumentos y retorno
        # El modo estricto de mypy implica esto, así que lo comprobamos primero.
        if policy.mypy_strict or "disallow_untyped_defs = true" in config_text:
            policy.require_argument_annotations = True
            policy.require_return_annotations = True
        # También buscar pistas textuales
        if "tipado estricto" in arch_text or "type hints obligatorios" in arch_text or \
           "tipado estricto" in issue_text or "type hints obligatorios" in issue_text:
            policy.require_argument_annotations = True
            policy.require_return_annotations = True

        # 3. Exportaciones explícitas (__all__)
        if 'exportación explícita' in arch_text or 'require_explicit_exports' in issue_text:
            policy.require_explicit_exports = True
            
        context.quality_policy = policy
        logging.info(f"Política de calidad derivada: {policy.model_dump_json()}")

    def _detect_testing_conventions(self, context: "RepositoryContext"):
        """Detects testing framework and mocking style from test files and conftest."""
        import ast as _ast
        has_pytest = False
        has_unittest = False
        has_mocker = False
        has_monkeypatch = False
        has_mock = False

        all_paths = list(context.test_index.keys())
        try:
            conftest_path = resolve_safe_path(self.root_path, "conftest.py")
            if os.path.exists(conftest_path):
                all_paths.append("conftest.py")
        except ValueError:
            pass

        for path in all_paths:
            try:
                content = self.get_file_content(path)
                tree = _ast.parse(content, filename=path)
                for node in _ast.walk(tree):
                    if isinstance(node, _ast.Import):
                        for alias in node.names:
                            if alias.name == "pytest":
                                has_pytest = True
                            elif alias.name == "unittest":
                                has_unittest = True
                    elif isinstance(node, _ast.ImportFrom):
                        module = node.module or ""
                        if module == "pytest":
                            has_pytest = True
                        elif module.startswith("unittest"):
                            has_unittest = True
                            if module == "unittest.mock":
                                has_mock = True
                    elif isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                        for arg in node.args.args:
                            if arg.arg == "mocker":
                                has_mocker = True
                            elif arg.arg == "monkeypatch":
                                has_monkeypatch = True
            except Exception:
                pass

        if has_pytest:
            context.detected_test_framework = "pytest"
        elif has_unittest:
            context.detected_test_framework = "unittest"

        # Mocking style detection
        if has_mocker:
            context.detected_mocking_instruction = "Usa el fixture 'mocker' de `pytest-mock` para el mocking."
        elif has_monkeypatch:
            context.detected_mocking_instruction = "Usa el fixture 'monkeypatch' de `pytest` para el patching."
        elif has_mock:
            context.detected_mocking_instruction = "Usa `unittest.mock` (`patch`, `MagicMock`) para aislar el componente."
        else:
            context.detected_mocking_instruction = "Aisla dependencias usando dependencias inyectables o librerías estándar."

    def _load_cache(self) -> "RepositoryIndexCache":
        if not os.path.exists(self.cache_file):
            return RepositoryIndexCache()
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return RepositoryIndexCache.model_validate_json(f.read())
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            logging.warning(f"No se pudo cargar o validar el caché del índice: {e}. Se reconstruirá desde cero.")
            return RepositoryIndexCache()

    def _save_cache(self, cache: "RepositoryIndexCache"):
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                f.write(cache.model_dump_json(indent=2))
            logging.info(f"Índice del repositorio cacheado en '{self.cache_file}'.")
        except (OSError, TypeError) as e:
            logging.error(f"No se pudo guardar el caché del índice: {e}")

    def _summarize_architecture_document(self, full_content: str, budget_tokens: int) -> str:
        """
        Summarizes the architecture document by prioritizing core sections and truncating history.
        """
        if not full_content:
            return ""

        # Split content by any markdown header (level 1 or 2)
        sections = re.split(r'(^#{1,2}\s+.*?$)', full_content, flags=re.MULTILINE)
        
        structured_sections: dict[str, str] = {}
        
        # If no headers detected, fallback immediately
        if len(sections) < 2:
            return full_content[:budget_tokens * 4] + ("" if len(full_content) <= budget_tokens * 4 else "\n... [TRUNCADO]")

        # Ensure we don't start with an empty body if there's no preamble
        if sections and not sections[0].strip():
            sections = sections[1:]
        elif sections and not sections[0].startswith('#'):
            # It's a preamble, keep it as 'preamble'
            structured_sections["# Preamble"] = sections[0].strip()
            sections = sections[1:]

        for i in range(0, len(sections), 2):
            header = sections[i].strip()
            body = sections[i+1].strip() if i + 1 < len(sections) else ""
            structured_sections[header] = body

        core_keywords = ["overview", "system", "component", "flow", "data", "arquitectura", "interface", "restriccion", "1.", "2.", "3.", "4.", "5.", "6.", "7."]
        
        core_content = ""
        historical_content = ""
        
        for header, body in structured_sections.items():
            header_lower = header.lower()
            if any(k in header_lower for k in core_keywords):
                core_content += f"{header}\n{body}\n\n"
            else:
                historical_content += f"{header}\n{body}\n\n"
        
        if not core_content.strip():
            core_content = full_content[:budget_tokens * 4]
            historical_content = ""

        core_tokens = len(core_content) // 4
        remaining_budget = budget_tokens - core_tokens

        if remaining_budget <= 200: # Reserve 200 tokens for truncation message
            if core_tokens > budget_tokens:
                logging.warning(f"El documento de arquitectura ({core_tokens} tokens) excede el límite de {budget_tokens} tokens. Las secciones principales serán truncadas.")
                return core_content[:budget_tokens * 4] + "\n... [SECCIONES PRINCIPALES TRUNCADAS]"
            return core_content

        # Add historical sections if budget allows
        if len(historical_content) // 4 <= remaining_budget:
            return core_content + historical_content
        else:
            return core_content + historical_content[:remaining_budget * 4] + "\n... [SECCIONES HISTÓRICAS TRUNCADAS]"

    def build_repository_context(self, issue_description: str, budget: "ContextBudget") -> "RepositoryContext":
        """Builds a comprehensive, indexed context of the entire repository, using a cache."""
        context = RepositoryContext()
        context.repository_map = self.generate_repository_map()
        
        # Apply architecture document budget
        arch_doc = self.read_architecture_document()
        context.architecture_document = self._summarize_architecture_document(arch_doc, budget.architecture_token_limit)
        
        cached_index = self._load_cache()
        
        context.project_configuration, context.dependency_files = self._scan_config_files()
        context.structured_config = self._extract_project_configuration(context.project_configuration, context.dependency_files)
        
        source_files: dict[str, PythonFileSummary] = {}
        test_files: dict[str, PythonFileSummary] = {}
        
        files_analyzed = 0
        files_from_cache = 0
        
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(full_path, self.root_path).replace("\\", "/")
                    
                    cached_summary = cached_index.source_index.get(relative_path) or cached_index.test_index.get(relative_path)
                    
                    try:
                        with open(full_path, "rb") as f:
                            current_hash = hashlib.sha256(f.read()).hexdigest()
                    except OSError:
                        continue

                    summary = None
                    if cached_summary and cached_summary.file_hash == current_hash:
                        summary = cached_summary
                        try:
                            with open(full_path, "r", encoding="utf-8") as text_f:
                                text_content = text_f.read()
                            summary.is_test = is_test_file(relative_path, text_content, context.structured_config)
                        except Exception:
                            pass
                        files_from_cache += 1
                    else:
                        summary = self._analyze_python_file(full_path, context.structured_config)
                        if summary:
                            files_analyzed += 1

                    if summary:
                        if summary.is_test:
                            test_files[summary.filepath] = summary
                        else:
                            source_files[summary.filepath] = summary
        
        logging.info(f"Análisis de índice completado. {files_analyzed} archivos analizados, {files_from_cache} cargados desde caché.")
        
        context.source_index = source_files
        context.test_index = test_files
        
        self._save_cache(RepositoryIndexCache(source_index=source_files, test_index=test_files))
        
        self._link_dependencies(context)
        self._detect_testing_conventions(context)

        self._derive_quality_policy(context, issue_description)

        self._detect_architecture_conflicts(context)

        # Calculate available token budget for files
        # This is a rough estimation of the fixed parts of the prompt
        base_prompt_tokens = estimate_repository_context_tokens(context, issue_description)
        available_tokens_for_files = budget.maximum_input_tokens - budget.reserved_output_tokens - base_prompt_tokens
        
        logging.info(f"Presupuesto de tokens disponible para archivos: {available_tokens_for_files}")

        self.select_relevant_files(
            context, 
            issue_description, 
            available_tokens_for_files,
            budget.maximum_full_files,
            budget.dependency_depth
        )

        return context

    def _link_dependencies(self, context: "RepositoryContext"):
        """Establishes relationships between files based on imports."""
        all_summaries = {**context.source_index, **context.test_index}
        all_py_files = list(all_summaries.keys())

        for path, summary in all_summaries.items():
            resolved_files = resolve_imported_files(summary.imports, self.root_path, all_py_files)
            for source_path in resolved_files:
                if source_path in context.source_index:
                    source_summary = context.source_index[source_path]
                    
                    if source_path not in summary.imported_files:
                        summary.imported_files.append(source_path)
                    if path not in source_summary.imported_by:
                        source_summary.imported_by.append(path)
                    
                    if summary.is_test and not source_summary.is_test:
                            if path not in source_summary.tested_by:
                                source_summary.tested_by.append(path)
                            if source_path not in summary.tests_for:
                                summary.tests_for.append(source_path)

    def select_relevant_files(
        self,
        context: "RepositoryContext",
        issue_description: str,
        token_budget: int,
        max_files: int,
        dependency_depth: int,
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
        
        # 2. Propagate scores through dependency graph recursively
        high_score_files = {p for p, s in scores.items() if s > 0}
        
        for i in range(dependency_depth):
            newly_boosted = set()
            # Propagate from high-score files to their direct dependencies
            for path in list(high_score_files):
                summary = all_summaries.get(path)
                if not summary:
                    continue
                
                # Boost tests for this source
                for test_path in summary.tested_by:
                    if test_path in scores and test_path not in high_score_files:
                        scores[test_path] += 3 / (i + 1)
                        newly_boosted.add(test_path)
                
                # Boost source for this test
                for source_path in summary.tests_for:
                    if source_path in scores and source_path not in high_score_files:
                        scores[source_path] += 3 / (i + 1)
                        newly_boosted.add(source_path)
                
                # Boost imported files
                for imp_path in summary.imported_files:
                    if imp_path in scores and imp_path not in high_score_files:
                        scores[imp_path] += 2 / (i + 1)
                        newly_boosted.add(imp_path)
                        
                # Boost files that import this
                for imp_by_path in summary.imported_by:
                    if imp_by_path in scores and imp_by_path not in high_score_files:
                        scores[imp_by_path] += 1 / (i + 1)
                        newly_boosted.add(imp_by_path)
            
            high_score_files.update(newly_boosted)

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
                    logging.info(f"Presupuesto de tokens para archivos ({token_budget}) agotado. Se detiene la selección.")
                    break # Token budget exceeded
            if files_selected >= max_files:
                logging.info(f"Límite de archivos completos ({max_files}) alcanzado. Se detiene la selección.")
                break

# Instancia global de contexto
# =====================================================================
# ESQUEMAS PYDANTIC PARA REFACTORIZACION Y DISENO DINAMICO LIBRE
# =====================================================================
class FileAction(BaseModel):
    filepath: str = Field(description="Ruta relativa completa del archivo (ej. 'core/billing.py', 'utils/helpers.py').")
    operation: str = Field(description="Operacion de ciclo de vida: 'CREATE' (crear nuevo), 'MODIFY' (modificar), 'DELETE' (eliminar).")
    file_type: str = Field(description="Categoria: 'production' (logica), 'test' (pytest o unittest según QualityGatePlan), 'config', o 'none'.")
    signatures: str = Field(description="Firma de las funciones, metodos o clases que deben residir en este archivo.")
    instructions: str = Field(description="Logica detallada de implementacion o requerimientos de refactorizacion.")

class ContextRequest(BaseModel):
    requested_files: list[str] = Field(default_factory=list, description="Lista de rutas de archivos adicionales requeridos.")
    requested_symbols: list[str] = Field(default_factory=list, description="Lista de símbolos (clases/funciones) adicionales requeridos.")
    reason: str = Field(default="", description="Razón por la que se necesita expandir el contexto.")

class ProjectDesign(BaseModel):
    is_context_request: bool = Field(default=False, description="True si necesitas más contexto antes de diseñar. Si es True, rellena 'context_request' y deja vacíos los demás campos.")
    context_request: ContextRequest | None = Field(default=None)
    architecture_justification: str = Field(default="", description="Razonamiento tecnico completo de por que se adopta esta topologia.")
    actions: list[FileAction] = Field(default_factory=list, description="Secuencia ordenada de acciones de archivos a ejecutar fisicamente.")
    dependencies: list[str] = Field(default_factory=list, description="Archivos existentes que se deben leer de forma micro como contexto.")

class ReviewFinding(BaseModel):
    filepath: str
    message: str

class CodeReviewResult(BaseModel):
    approved: bool
    design_conflict: bool = False
    findings: list[ReviewFinding] = Field(default_factory=list)

class QualityGatePlan(BaseModel):
    run_tests: bool = False
    test_framework: Literal["pytest", "unittest", "none"] = "none"
    run_mypy: bool = False
    run_ruff: bool = False
    run_vulture: bool = False

class PromptBudget(BaseModel):
    max_input_tokens: int
    reserved_output_tokens: int
    used_tokens: int = 0
    def can_add(self, tokens: int) -> bool:
        return (self.used_tokens + tokens) <= (self.max_input_tokens - self.reserved_output_tokens)
    def add(self, tokens: int):
        self.used_tokens += tokens
    @property
    def remaining(self) -> int:
        return max(0, self.max_input_tokens - self.reserved_output_tokens - self.used_tokens)

def ensure_prompt_fits(prompt: str, budget: PromptBudget, label: str) -> None:
    estimated_tokens = len(prompt) // 4
    maximum = budget.max_input_tokens - budget.reserved_output_tokens
    if estimated_tokens > maximum:
        raise PreflightError(f"{label} excede PromptBudget: {estimated_tokens} > {maximum}")

def add_required_or_fail(budget: PromptBudget, text: str, label: str) -> None:
    tokens = len(text) // 4
    if not budget.can_add(tokens):
        raise PreflightError(f"{label} no cabe en PromptBudget.")
    budget.add(tokens)

class PromptPayload(BaseModel):
    content: str
    estimated_tokens: int
    omitted_files: list[str] = Field(default_factory=list)

class PythonQualityPolicy(BaseModel):
    require_argument_annotations: bool = Field(default=False, description="Si se requieren anotaciones de tipo para los argumentos de las funciones.")
    require_return_annotations: bool = Field(default=False, description="Si se requieren anotaciones de tipo para el retorno de las funciones.")
    mypy_strict: bool = Field(default=False, description="Si MyPy debe ejecutarse en modo estricto.")
    require_explicit_exports: bool = Field(default=False, description="Si los archivos de producción deben tener `__all__`.")


def parse_pyproject(content: str) -> dict:
    import tomllib
    result = {"python_version": None, "tools": {}, "dependencies": [], "dev_dependencies": []}
    try:
        data = tomllib.loads(content)
        # Python version
        req_py = data.get("project", {}).get("requires-python")
        if not req_py:
            req_py = data.get("tool", {}).get("poetry", {}).get("dependencies", {}).get("python")
        result["python_version"] = str(req_py) if req_py else None
        
        # Tools
        result["tools"] = data.get("tool", {})
        
        # PEP 621 dependencies
        for dep in data.get("project", {}).get("dependencies", []):
            dep_name = re.split(r'[=><~\[]', dep)[0].strip()
            if dep_name: result["dependencies"].append(dep_name)
        for group_deps in data.get("project", {}).get("optional-dependencies", {}).values():
            for dep in group_deps:
                dep_name = re.split(r'[=><~\[]', dep)[0].strip()
                if dep_name: result["dev_dependencies"].append(dep_name)
                
        # Poetry dependencies
        poetry = data.get("tool", {}).get("poetry", {})
        for dep in poetry.get("dependencies", {}).keys():
            if dep != "python": result["dependencies"].append(dep)
        for dep in poetry.get("dev-dependencies", {}).keys():
            result["dev_dependencies"].append(dep)
        for group in poetry.get("group", {}).values():
            for dep in group.get("dependencies", {}).keys():
                result["dev_dependencies"].append(dep)
    except Exception:
        pass
    return result

def parse_requirements(content: str) -> list[str]:
    deps = []
    for line in content.splitlines():
        line = line.split('#')[0].strip()
        if line and not line.startswith('-'):
            dep_name = re.split(r'[=><~\[]', line)[0].strip()
            if dep_name: deps.append(dep_name)
    return deps

def parse_pipfile(content: str) -> dict:
    import tomllib
    result = {"dependencies": [], "dev_dependencies": []}
    try:
        data = tomllib.loads(content)
        result["dependencies"] = list(data.get("packages", {}).keys())
        result["dev_dependencies"] = list(data.get("dev-packages", {}).keys())
    except Exception:
        pass
    return result

def parse_poetry_lock(content: str) -> list[str]:
    import tomllib
    deps = []
    try:
        data = tomllib.loads(content)
        for pkg in data.get("package", []):
            name = pkg.get("name")
            if name: deps.append(name)
    except Exception:
        pass
    return deps

def parse_setup_cfg(content: str) -> list[str]:
    import configparser
    deps = []
    try:
        config = configparser.ConfigParser()
        config.read_string(content)
        if config.has_option("options", "install_requires"):
            reqs = config.get("options", "install_requires").splitlines()
            for r in reqs:
                dep_name = re.split(r'[=><~\[]', r.strip())[0].strip()
                if dep_name: deps.append(dep_name)
    except Exception:
        pass
    return deps

def parse_setup_py(content: str) -> dict:
    """Extrae literales seguros de setup() usando AST sin ejecutar código."""
    result = {"install_requires": [], "extras_require": {}, "python_requires": None}
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "setup":
                for kw in getattr(node, "keywords", []):
                    if kw.arg == "python_requires" and isinstance(kw.value, ast.Constant):
                        result["python_requires"] = kw.value.value
                    elif kw.arg == "install_requires" and isinstance(kw.value, (ast.List, ast.Tuple)):
                        for elt in kw.value.elts:
                            if isinstance(elt, ast.Constant):
                                dep_name = re.split(r'[=><~\[]', str(elt.value).strip())[0].strip()
                                if dep_name:
                                    result["install_requires"].append(dep_name)
                    elif kw.arg == "extras_require" and isinstance(kw.value, ast.Dict):
                        for k, v in zip(kw.value.keys, kw.value.values):
                            if isinstance(k, ast.Constant) and isinstance(v, (ast.List, ast.Tuple)):
                                ex_deps = []
                                for elt in v.elts:
                                    if isinstance(elt, ast.Constant):
                                        dep_name = re.split(r'[=><~\[]', str(elt.value).strip())[0].strip()
                                        if dep_name:
                                            ex_deps.append(dep_name)
                                result["extras_require"][k.value] = ex_deps
    except Exception:
        pass
    return result

class PythonProjectConfiguration(BaseModel):
    python_version: str | None = None
    pytest_paths: list[str] = Field(default_factory=list)
    pytest_patterns: list[str] = Field(default_factory=list)
    mypy_enabled: bool = False
    mypy_strict: bool = False
    mypy_targets: list[str] = Field(default_factory=list, description="Archivos/paquetes explícitos declarados en la sección [mypy] files = ...")
    ruff_enabled: bool = False
    vulture_enabled: bool = False
    dependencies: list[str] = Field(default_factory=list)
    dev_dependencies: list[str] = Field(default_factory=list)
    detected_quality_tools: list[str] = Field(default_factory=list)

class SecurityAuditResult(BaseModel):
    approved: bool
    findings: list[str] = Field(default_factory=list)

class ArchitectureConflict(BaseModel):
    type: str = Field(description="Tipo de conflicto (ej. 'MISSING_COMPONENT', 'OUTDATED_TOOL')")
    description: str = Field(description="Descripción del conflicto.")
    architecture_reference: str = Field(description="Cita o referencia del documento de arquitectura.")
    repository_evidence: list[str] = Field(description="Evidencia del repositorio que contradice la arquitectura.")
    blocks_execution: bool = Field(default=False, description="Si el conflicto es tan grave que bloquea la ejecución.")

class PythonFileSummary(BaseModel):
    filepath: str
    module_name: str
    is_test: bool
    classes: list[str]
    functions: list[str]
    signatures: dict[str, str] = Field(description="A mapping of symbol names to their full signature strings.")
    imports: list[str]
    exports: list[str]
    docstring_summary: str
    referenced_symbols: list[str]
    file_hash: str
    estimated_tokens: int
    tests_for: list[str] = Field(default_factory=list, description="List of source files this file tests.")
    tested_by: list[str] = Field(default_factory=list, description="List of test files that cover this source file.")
    imported_files: list[str] = Field(default_factory=list, description="List of source files this file imports.")
    imported_by: list[str] = Field(default_factory=list, description="List of files that import this file.")

# Custom Exceptions
class RepositoryIndexCache(BaseModel):
    source_index: dict[str, PythonFileSummary] = Field(default_factory=dict)
    test_index: dict[str, PythonFileSummary] = Field(default_factory=dict)

class ContractGenerationError(Exception):
    """Custom exception for failures during acceptance contract generation."""

class PreflightError(Exception):
    """Custom exception for failures during environment preflight checks."""

class RequiredCall(BaseModel):
    name: str
    count: int = 1

_VALID_VALIDATION_METHODS = {"protected_test", "required_test", "semantic_reviewer"}

class PreservedBehavior(BaseModel):
    description: str
    affected_files: list[str]
    validation_method: Literal["protected_test", "required_test", "semantic_reviewer"]
    protected_tests: list[str] = Field(default_factory=list)

    def validate_governance(self, contract: "AcceptanceContract") -> list[str]:
        """Validates that the chosen validation_method has a corresponding verifiable artefact."""
        gov_errors = []

        if self.validation_method in ("protected_test", "required_test"):
            if not self.protected_tests:
                gov_errors.append(
                    f"PreservedBehavior '{self.description[:60]}' usa '{self.validation_method}' "
                    "pero no declara ningún protected_test."
                )
            else:
                # Flatten the dict values — keys are file paths, values are test-name lists
                required_names = {
                    name
                    for names in contract.required_tests.values()
                    for name in names
                }
                protected_names = {
                    name
                    for names in contract.protected_tests.values()
                    for name in names
                }
                # required_test method → must appear in required_tests
                # protected_test method → must appear in protected_tests
                if self.validation_method == "required_test":
                    declared_names = required_names
                    registry_label = "required_tests"
                else:
                    declared_names = protected_names
                    registry_label = "protected_tests"

                for t in self.protected_tests:
                    if t not in declared_names:
                        gov_errors.append(
                            f"PreservedBehavior '{self.description[:60]}': test '{t}' "
                            f"no está registrado en {registry_label} del contrato."
                        )
        return gov_errors

class FileContract(BaseModel):
    filepath: str
    required_testing_techniques: set[str] = Field(default_factory=set)
    forbidden_testing_techniques: set[str] = Field(default_factory=set)
    required_symbols: list[str] = Field(default_factory=list) # TODO: Deprecate in favor of more specific rules
    preserved_behaviors: list[PreservedBehavior] = Field(default_factory=list, description="Comportamientos de alto nivel que deben preservarse en este archivo.")
    preserved_signatures: dict[str, str] = Field(default_factory=dict)
    required_exports: list[str] = Field(default_factory=list)
    required_imports: list[str] = Field(default_factory=list)
    forbidden_imports: list[str] = Field(default_factory=list)
    required_calls: dict[str, list[RequiredCall]] = Field(default_factory=dict)
    forbidden_constructs: list[str] = Field(default_factory=list)
    required_patterns: list[str] = Field(default_factory=list)
    required_decorators: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list, description="Nombres de los tests que deben ser implementados en este archivo.")
    protected_tests: list[str] = Field(default_factory=list, description="Nombres de los tests existentes que deben ser preservados.")
    required_structures: dict[str, str] = Field(default_factory=dict, description="Validaciones estructurales requeridas para variables en este archivo.")
    
class ContextBudget(BaseModel):
    maximum_input_tokens: int = Field(default=128_000, description="Capacidad máxima de tokens del modelo.")
    reserved_output_tokens: int = Field(default=8_000, description="Tokens reservados para la respuesta del modelo.")
    maximum_full_files: int = Field(default=15, description="Número máximo de archivos a incluir completos.")
    dependency_depth: int = Field(default=2, description="Niveles de dependencias a seguir.")
    architecture_token_limit: int = Field(default=5_000, description="Límite de tokens para el documento de arquitectura.")

class RepositoryContext(BaseModel):
    repository_map: str = ""
    architecture_document: str = ""
    source_index: dict[str, PythonFileSummary] = Field(default_factory=dict)
    test_index: dict[str, PythonFileSummary] = Field(default_factory=dict)
    project_configuration: dict[str, str] = Field(default_factory=dict)
    dependency_files: dict[str, str] = Field(default_factory=dict)
    detected_test_framework: str | None = None
    detected_mocking_instruction: str = "Usa el mecanismo de mocks o fixtures ya adoptado por el repositorio."
    quality_policy: "PythonQualityPolicy" = Field(default_factory=PythonQualityPolicy)
    detected_quality_tools: list[str] = Field(default_factory=list)
    relevant_source_files: dict[str, str] = Field(default_factory=dict)
    relevant_test_files: dict[str, str] = Field(default_factory=dict)
    architecture_conflicts: list["ArchitectureConflict"] = Field(default_factory=list)
    structured_config: "PythonProjectConfiguration" = Field(default_factory=PythonProjectConfiguration)

class AcceptanceContract(BaseModel):
    required_final_files: set[str] = Field(default_factory=set, description="Archivos que deben existir al finalizar la tarea.")
    required_new_files: set[str] = Field(default_factory=set, description="Archivos que deben ser creados.")
    required_modified_files: set[str] = Field(default_factory=set, description="Archivos que deben ser modificados.")
    required_deleted_files: set[str] = Field(default_factory=set, description="Archivos que deben ser eliminados.")
    preserved_files: set[str] = Field(default_factory=set, description="Archivos existentes que son relevantes pero no deben ser modificados.")
    relevant_context_files: set[str] = Field(default_factory=set, description="Archivos existentes que son relevantes como contexto para la generación de código.")

    required_tests: dict[str, list[str]] = Field(default_factory=dict)
    protected_tests: dict[str, list[str]] = Field(default_factory=dict, description="Tests existentes que no deben romperse ni eliminarse.")
    preserved_signatures: dict[str, dict[str, str]] = Field(default_factory=dict, description="Firmas de símbolos que deben preservarse. {filepath: {symbol_name: signature_string}}")
    preserved_behaviors: list[PreservedBehavior] = Field(default_factory=list, description="Comportamientos existentes que no deben romperse.")

    forbidden_test_names: list[str] = Field(default_factory=list)
    forbidden_constructs: dict[str, list[str]] = Field(default_factory=dict, description="Pattern: {filepath_glob: [construct_name]}")
    required_exports: dict[str, list[str]] = Field(default_factory=dict)
    
    required_quality_tools: set[str] = Field(default_factory=set)
    forbidden_quality_tools: set[str] = Field(default_factory=set)
    required_testing_techniques: set[str] = Field(default_factory=set)
    forbidden_testing_techniques: set[str] = Field(default_factory=set)

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


class ContractCapability(BaseModel):
    validation_type: str
    implemented: bool
    validator_name: str | None = None
    supported_values: set[str] = Field(default_factory=set)

# =====================================================================
# REGISTRO DE CAPACIDADES DEL VALIDADOR DE CONTRATOS
# =====================================================================
_SUPPORTED_AST_CONSTRUCTS = {"continue", "pass"}
_SUPPORTED_CODE_PATTERNS = {"log_before_raise"}
_SUPPORTED_STRUCTURE_CHECKS = {"has_aliases"}
def validate_relevant_context_files(repo_context: "RepositoryContext", contract: "AcceptanceContract") -> list[str]:
    """Validates that relevant_context_files listed in the contract actually exist in the repository index."""
    errors = []
    all_known = set(repo_context.source_index.keys()) | set(repo_context.test_index.keys())
    for f in contract.relevant_context_files:
        if f not in all_known:
            errors.append(f"relevant_context_files: '{f}' no existe en el índice del repositorio.")
    return errors

def canonicalize_testing_technique(technique: str) -> str:
    normalized = technique.strip().lower()

    aliases = {
        "mocker": "pytest-mock",
        "pytest-mock": "pytest-mock",
        "monkeypatch": "monkeypatch",
        "unittest.mock.patch": "unittest.mock.patch",
    }

    return aliases.get(normalized, normalized)

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


def validate_contract_consistency(contract: AcceptanceContract) -> tuple[bool, list[str]]:
    """Valida la consistencia interna del contrato para evitar contradicciones lógicas."""
    errors = []
    all_new = set(contract.required_new_files)
    all_mod = set(contract.required_modified_files)
    all_del = set(contract.required_deleted_files)
    all_pres = set(contract.preserved_files)
    all_final = set(contract.required_final_files)

    for f in (all_new & all_del): errors.append(f"Inconsistencia: Archivo marcado para crear y borrar simultáneamente: {f}")
    for f in (all_mod & all_pres): errors.append(f"Inconsistencia: Archivo marcado para modificar y preservar simultáneamente: {f}")
    for f in (all_final & all_del): errors.append(f"Inconsistencia: Archivo requerido en estado final pero marcado para borrar: {f}")
    for f in (all_new & all_mod): errors.append(f"Inconsistencia: Archivo marcado para crear y modificar simultáneamente: {f}")
    for f in (all_pres & all_new): errors.append(f"Inconsistencia: Archivo marcado para preservar y crear simultáneamente: {f}")
    for f in (all_pres & all_del): errors.append(f"Inconsistencia: Archivo marcado para preservar y borrar simultáneamente: {f}")

    return not errors, errors

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


def _create_file_contract(filepath: str, contract: AcceptanceContract) -> "FileContract":
    """Extracts a file-specific contract from the global acceptance contract."""
    
    file_contract = FileContract(filepath=filepath)
    
    # preserved_signatures
    if filepath in contract.preserved_signatures:
        file_contract.preserved_signatures = contract.preserved_signatures[filepath]
    # preserved_behaviors (only those that affect this file, or affect all if empty)
    for pb in contract.preserved_behaviors:
        if not pb.affected_files or filepath in pb.affected_files:
            file_contract.preserved_behaviors.append(pb)

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
        
    # required_decorators
    for path_glob, decorators in contract.required_decorators.items():
        if fnmatch.fnmatch(filepath, path_glob):
            file_contract.required_decorators.extend(decorators)

    # --- New fields ---
    if filepath in contract.required_tests:
        file_contract.required_tests = contract.required_tests[filepath]

    if filepath in contract.protected_tests:
        file_contract.protected_tests = contract.protected_tests[filepath]

    if filepath in contract.required_structures:
        file_contract.required_structures = contract.required_structures[filepath]
    
    file_contract.required_testing_techniques = contract.required_testing_techniques
    file_contract.forbidden_testing_techniques = contract.forbidden_testing_techniques

    for tech in file_contract.required_testing_techniques:
        if "unittest.mock.patch" in tech.lower():
            if "from unittest.mock import patch" not in file_contract.required_imports:
                file_contract.required_imports.append("from unittest.mock import patch")

    for tech in file_contract.forbidden_testing_techniques:
        if "pytest-mock" in tech.lower() or "mocker" in tech.lower():
            if "pytest_mock" not in file_contract.forbidden_imports:
                file_contract.forbidden_imports.append("pytest_mock")

    return file_contract

def agent_generate_acceptance_contract(title: str, description: str, repository_context: RepositoryContext, runtime: RuntimeClients) -> AcceptanceContract:
    """
    Generates a structured acceptance contract from the issue description, repository context, and architecture.
    """
    logging.info("Generando Contrato de Aceptación a partir del Issue y contexto del repositorio...")
    
    budget_contract = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)

    project_config_json = repository_context.structured_config.model_dump_json(indent=2)
    policy_summary = json.dumps(repository_context.quality_policy.model_dump(), indent=2)

    # Reservar contexto obligatorio
    base_instructions_len = 2000 # estimación conservadora
    mandatory_tokens = base_instructions_len + (len(title) + len(description) + len(project_config_json) + len(policy_summary)) // 4
    if not budget_contract.can_add(mandatory_tokens):
        raise PreflightError("El contexto obligatorio excede el presupuesto del Contrato.")
    budget_contract.add(mandatory_tokens)

    # Priority 1: architecture doc
    arch_text = repository_context.architecture_document or "[No se encontro documento de arquitectura.]"
    arch_tokens = len(arch_text) // 4
    if not budget_contract.can_add(arch_tokens):
        max_chars = budget_contract.remaining * 4
        arch_text = arch_text[:max_chars]
        logging.warning("architecture_document truncado.")
        arch_tokens = len(arch_text) // 4
    budget_contract.add(arch_tokens)

    # Priority 2: compact global index
    all_summaries = {**repository_context.source_index, **repository_context.test_index}
    global_index_summary = {
        fp: {"classes": summary.classes, "functions": summary.functions}
        for fp, summary in all_summaries.items()
    }
    global_index_json = json.dumps(global_index_summary, indent=2)
    idx_tokens = len(global_index_json) // 4
    if budget_contract.can_add(idx_tokens):
        budget_contract.add(idx_tokens)
    else:
        max_chars = budget_contract.remaining * 4
        global_index_json = global_index_json[:max_chars]
        budget_contract.add(len(global_index_json) // 4)

    # Priority 3: relevant file metadata
    relevant_files_metadata = {}
    for fp in list(repository_context.relevant_source_files.keys()) + list(repository_context.relevant_test_files.keys()):
        summary = all_summaries.get(fp)
        if summary:
            relevant_files_metadata[fp] = summary.model_dump(exclude={'file_hash', 'estimated_tokens', 'referenced_symbols', 'docstring_summary'})
    relevant_metadata_json = json.dumps(relevant_files_metadata, indent=2)
    meta_tokens = len(relevant_metadata_json) // 4
    if budget_contract.can_add(meta_tokens):
        budget_contract.add(meta_tokens)
    else:
        relevant_metadata_json = relevant_metadata_json[:budget_contract.remaining * 4]
        budget_contract.add(len(relevant_metadata_json) // 4)

    # Priority 4: full file contents (only what fits)
    relevant_files_context = ""
    if repository_context.relevant_source_files or repository_context.relevant_test_files:
        relevant_files_context += "\n\nCONTENIDO DE ARCHIVOS RELEVANTES (PRE-SELECCIONADOS POR RELEVANCIA):\n"
        for path, file_content in {**repository_context.relevant_source_files, **repository_context.relevant_test_files}.items():
            frag = f"--- INICIO {path} ---\n{file_content}\n--- FIN {path} ---\n"
            tok = len(frag) // 4
            if budget_contract.can_add(tok):
                relevant_files_context += frag
                budget_contract.add(tok)

    prompt = f"""
    Actúas como un Quality Assurance Lead y Arquitecto de Pruebas. Tu tarea es leer una especificación de requisitos de un Issue y traducirla a un contrato de aceptación técnico y estricto en formato JSON.

    Este contrato define las reglas inmutables que el código generado debe cumplir.

    FUENTES DE INFORMACIÓN:
    1.  REQUISITOS DEL ISSUE (El 'qué' se debe cambiar):
       - Título: {title}
       - Requisitos: {description}

    2.  DOCUMENTO DE ARQUITECTURA (El 'porqué' de las decisiones de diseño):
       --- INICIO DOCUMENTO ---
       {arch_text}
       --- FIN DOCUMENTO ---

    3.  RESUMEN GLOBAL DEL CÓDIGO (Todas las clases y funciones del repo):
       --- INICIO RESUMEN ÍNDICE ---
       {global_index_json}
       --- FIN RESUMEN ÍNDICE ---

    4.  METADATOS DE ARCHIVOS RELEVANTES (Relaciones, tests e imports detectados):
       --- INICIO METADATOS RELEVANTES ---
       {relevant_metadata_json}
       --- FIN METADATOS RELEVANTES ---

    5.  CONFIGURACIÓN DEL PROYECTO (Reglas de linters, dependencias base):
       --- INICIO CONFIGURACIÓN ---
       {project_config_json}
       --- FIN CONFIGURACIÓN ---

    6.  POLÍTICA DE CALIDAD DERIVADA (Reglas de alto nivel inferidas del repositorio):
        {policy_summary}

    {relevant_files_context}

    Analiza TODAS las fuentes de información para derivar el contrato. Por ejemplo:
    - Si el Issue pide modificar un archivo, el contrato debe incluirlo en `required_modified_files`.
    - Si la `POLÍTICA DE CALIDAD` indica `require_explicit_exports: true`, el contrato debe generar reglas en `required_exports` para los archivos de producción relevantes.
    - Si la `POLÍTICA DE CALIDAD` indica `require_argument_annotations: true`, el contrato debe reflejarlo en sus reglas, aunque el validador `validate_code_quality` ya lo compruebe.
    - Si la arquitectura o la política prohíben `pytest-mock`, el contrato debe reflejarlo en `forbidden_testing_techniques` y `forbidden_imports`.
    - Si el Issue menciona una funcionalidad que ya tiene tests (visible en el ÍNDICE DE TESTS), el contrato debe listarlos en `protected_tests` para asegurar que no se rompan.
    - Si el código existente (visible en ARCHIVOS RELEVANTES) usa un patrón (ej. `logger.warning` antes de `raise`), el contrato debe exigirlo en `required_patterns`.
    - Si `pyproject.toml` define una regla de Ruff, el contrato puede reforzarla en `required_quality_tools`.

    Extrae las siguientes reglas:
    - `required_final_files`: Archivos que deben existir al finalizar la tarea.
    - `required_new_files`: Archivos que deben ser creados.
    - `required_modified_files`: Archivos que deben ser modificados.
    - `required_deleted_files`: Archivos que deben ser eliminados.
    - `preserved_files`: Archivos existentes que son relevantes pero no deben ser modificados. Si un archivo tiene tests protegidos, debería estar aquí.
    - `relevant_context_files`: Archivos de contexto relevantes.
    - `required_tests`: Pruebas obligatorias para la **nueva** funcionalidad.
    - `protected_tests`: Tests existentes que no deben romperse ni eliminarse. Extrae esto del índice del repositorio, especialmente los tests que cubren los módulos a modificar.
    - `forbidden_test_names`: Nombres de pruebas que están explícitamente prohibidos.
    - `preserved_signatures`: Firmas de símbolos que deben preservarse porque otros módulos dependen de ellas. Extrae las firmas completas del índice. Formato: `{"module.py": {"PublicClass": "class PublicClass(arg1: int)", "public_function": "def public_function()"}}`.
    - `preserved_behaviors`: Comportamientos de alto nivel que no pueden ser expresados con reglas AST o tests. **Usa este campo como último recurso.** Prioriza siempre convertir un comportamiento en una regla concreta en `protected_tests`, `required_tests`, `required_patterns`, etc. Si usas este campo, el Code Reviewer lo validará semánticamente.
    - `forbidden_constructs`: Un diccionario donde la clave es un glob de ruta de archivo (ej. `src/services/example_service*.py`) y el valor es una lista de constructos prohibidos ('continue', 'pass').
    - `required_exports`: Símbolos que deben estar en `__all__`.
    - `required_calls`: Especifica que una función debe llamar a otra. Ej: `{"src/utils/data_normalization.py": {"normalize_data_item": [{"name": "dependency_function", "count": 1}]}}`.
    - `required_patterns`: Patrones de código obligatorios. Ej: `{"src/services/example_service.py": ["log_before_raise"]}`.
    - `required_structures`: Validaciones sobre estructuras de datos. Ej: `{"src/utils/data_normalization.py": {"PUBLIC_MAPPING": "has_aliases"}}`.
    - `required_imports` / `forbidden_imports`: Reglas sobre importaciones. Ej: `{"tests/*": ["from unittest.mock import patch"]}` y `{"tests/*": ["pytest_mock"]}`.
    - `required_decorators`: Decoradores requeridos en un archivo. Ej: `{"src/api/endpoints.py": ["@app.route"]}`.
    - `required_quality_tools`: Herramientas de calidad (linters/checkers) que deben usarse (ej. "mypy", "ruff").
    - `forbidden_quality_tools`: Herramientas de calidad prohibidas (ej. "flake8").
    - `required_testing_techniques`: Técnicas específicas de pruebas obligatorias (ej. "unittest.mock.patch").
    - `forbidden_testing_techniques`: Técnicas de pruebas explícitamente prohibidas (ej. "pytest-mock").

    Si un campo no es aplicable, déjalo como una lista o diccionario vacío.
    Responde únicamente con el JSON que se ajuste al esquema `AcceptanceContract`.
    """
    
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AcceptanceContract,
        temperature=0.1
    )
    
    try:
        ensure_prompt_fits(prompt, budget_contract, "Acceptance Contract")
        response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
        contract = AcceptanceContract.model_validate_json(response.text)
        logging.info("Contrato de Aceptación generado con éxito.")
        return contract
    except Exception as e:
        logging.error(f"No se pudo generar o validar el Contrato de Aceptación: {e}")
        raise ContractGenerationError(f"Fallo crítico al generar el Contrato de Aceptación: {e}") from e

def extract_code(text, language=None):
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
    pattern = rf"{MD_FENCE}{language}\s*(.*?)\s*{MD_FENCE}" if language else rf"{MD_FENCE}(?:[a-zA-Z0-9_\-\.]+)?\s*(.*?)\s*{MD_FENCE}"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
        
    pattern_any = rf"{MD_FENCE}(?:[a-zA-Z0-9_\-\.]+)?\s*(.*?)\s*{MD_FENCE}"
    match_any = re.search(pattern_any, text, re.DOTALL)
    if match_any:
        return match_any.group(1).strip()

    return text.strip()

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

def run_static_analysis(generated_filepaths: list[str], plan: "QualityGatePlan", test_paths: Collection[str] | None = None) -> tuple[bool, str]:
    """
    Ejecuta Ruff y/o Vulture según el plan de gates.
    """
    success = True
    report = ""
    
    py_files = [f for f in generated_filepaths if f.endswith(".py") and os.path.exists(f)]
    if not py_files:
        return True, "No hay archivos Python para validacion estatica."

    if not plan.run_ruff and not plan.run_vulture:
        return True, "Ruff y Vulture deshabilitados por el plan de gates."

    if plan.run_ruff:
        ruff_files = [f for f in py_files if "vulture_whitelist.py" not in f]
        logging.info(f"Ejecutando Ruff en {len(ruff_files)} archivos...")
        try:
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

    if plan.run_vulture:
        # Para evitar falsos positivos, Vulture debe analizar producción + tests juntos
        # Si se le pasa un set de tests combinados, lo usamos para identificar producción,
        # pero pasamos AMBOS al binario de vulture para que resuelva referencias cruzadas.
        prod_files = []
        if test_paths is not None:
            prod_files = [f for f in py_files if f not in test_paths]
        else:
            prod_files = [f for f in py_files if not is_test_file(f)]
            
        if prod_files:
            # Añadimos los test paths al análisis de vulture para que vea el uso de los fixtures/mocks
            all_files_to_analyze = prod_files.copy()
            if test_paths:
                all_files_to_analyze.extend(list(test_paths))
            logging.info(f"Ejecutando Vulture en {len(all_files_to_analyze)} archivos (prod + tests)...")
            try:
                result_v = subprocess.run([sys.executable, "-m", "vulture"] + all_files_to_analyze, capture_output=True, text=True, timeout=300)
                if result_v.returncode != 0:
                    success = False
                    report += f"\n[Vulture Detector] Codigo muerto detectado:\n{result_v.stdout or result_v.stderr}"
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                success = False
                report += f"\n[Fallo de Infraestructura] No se pudo ejecutar Vulture: {e}. Asegúrate de que está instalado y en el PATH."
        
    return success, report

def reload_code_after_ruff(generated_files: dict[str, str], context_manager: "RepositoryContextManager") -> None:
    for path in generated_files:
        if os.path.exists(path):
            generated_files[path] = context_manager.get_file_content(path)

# =====================================================================
# CAPA DE VALIDACIÓN DE CALIDAD DE CÓDIGO (NUEVO)
# =====================================================================
def validate_code_quality(code: str, filepath: str, policy: "PythonQualityPolicy") -> tuple[bool, str]:
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
    if policy.require_argument_annotations or policy.require_return_annotations:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Validar argumentos
                if policy.require_argument_annotations:
                    for arg in node.args.args:
                        if arg.arg not in ('self', 'cls') and arg.annotation is None:
                            errors.append(f"Argumento '{arg.arg}' en la función '{node.name}' (línea {arg.lineno}) no tiene type hint.")
                # Validar retorno (excepto en constructores)
                if policy.require_return_annotations:
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

def _check_tests(tree: ast.AST, filepath: str, contract: AcceptanceContract, repo_context=None) -> list[str]:
    errors = []
    # Collect all function names defined in this file
    test_names = {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    # Use repo_context for test file detection when available
    project_config = repo_context.structured_config if repo_context else None

    # forbidden_test_names applies globally to every test file, regardless of whether
    # it appears in required_tests or protected_tests.
    if is_test_file(filepath, project_config=project_config):
        for forbidden in contract.forbidden_test_names:
            if forbidden in test_names:
                errors.append(f"Test prohibido por contrato encontrado en {filepath}: '{forbidden}'")

    # required / protected checks only apply to files explicitly listed in the contract.
    if filepath in contract.required_tests:
        for required_test in contract.required_tests[filepath]:
            if required_test not in test_names:
                errors.append(f"Falta la prueba obligatoria por contrato: {required_test}")

    for protected_test in contract.protected_tests.get(filepath, []):
        if protected_test not in test_names:
            errors.append(f"Se eliminó el test protegido: {protected_test}")

    # If the file is not a test file at all and not listed in either set, nothing to check.
    if not is_test_file(filepath, project_config=project_config) and filepath not in contract.required_tests and filepath not in contract.protected_tests:
        return []

    return errors

def _check_imports(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    errors = []

    # --- Check required imports ---
    # First, determine which imports are required for this file
    all_required_imports = set()
    for path_glob, required_list in contract.required_imports.items():
        if fnmatch.fnmatch(filepath, path_glob):
            all_required_imports.update(required_list)

    # If there are required imports, build a set of found imports and check
    if all_required_imports:
        found_imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    found_imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    found_imports.add(f"from {module} import {alias.name}")
        
        missing_imports = all_required_imports - found_imports
        for missing in sorted(list(missing_imports)):
            errors.append(f"Import obligatorio '{missing}' no encontrado en {filepath}")

    # --- Check forbidden imports ---
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
            caller_found = False
            for func_node in ast.walk(tree):
                if isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)) and func_node.name == func_name:
                    caller_found = True
                    for call_info in required_calls:
                        callee_name = call_info.name
                        required_count = call_info.count
                        
                        actual_count = 0
                        for call_node in ast.walk(func_node):
                            if isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Name) and call_node.func.id == callee_name or isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Attribute) and call_node.func.attr == callee_name:
                                actual_count += 1
                        
                        if actual_count < required_count:
                            errors.append(f"En {filepath}, la función '{func_name}' debe llamar a '{callee_name}' al menos {required_count} veces, pero solo se encontraron {actual_count}.")
            
            if not caller_found:
                errors.append(f"No existe la función requerida '{func_name}' en {filepath}.")
    return errors

def _check_structures(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    errors = []
    if filepath in contract.required_structures:
        for var_name, check_type in contract.required_structures[filepath].items():
            if check_type in _SUPPORTED_STRUCTURE_CHECKS:
                structure_found = False
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id == var_name:
                                structure_found = True
                                if not isinstance(node.value, ast.Dict):
                                    errors.append(f"La estructura '{var_name}' en {filepath} no es un diccionario.")
                                    continue
                                values = [elt.value for elt in node.value.values if isinstance(elt, ast.Constant)]
                                if len(values) == len(set(values)):
                                    errors.append(f"La estructura '{var_name}' en {filepath} no contiene alias (valores duplicados).")
                if not structure_found:
                    errors.append(f"La estructura requerida '{var_name}' no se encontró en {filepath}.")
            else:
                errors.append(f"Validación de estructura '{check_type}' para '{var_name}' en {filepath} no está implementada o soportada por el validador AST.")
    return errors

def _get_decorator_name(decorator_node: ast.expr) -> str:
    """Recursivamente obtiene el nombre completo (dotted) de un decorador a partir de su nodo AST."""
    if isinstance(decorator_node, ast.Name):
        return decorator_node.id
    if isinstance(decorator_node, ast.Attribute):
        return f"{_get_decorator_name(decorator_node.value)}.{decorator_node.attr}"
    if isinstance(decorator_node, ast.Call):
        return _get_decorator_name(decorator_node.func)
    return ""

def _check_decorators(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    """Valida que los decoradores requeridos por el contrato se usen en el archivo."""
    errors = []
    
    all_required_decorators = set()
    for path_glob, required_list in contract.required_decorators.items():
        if fnmatch.fnmatch(filepath, path_glob):
            # Elimina el '@' si está presente, ya que los nodos AST no lo incluyen.
            all_required_decorators.update([d.lstrip('@') for d in required_list])

    if not all_required_decorators:
        return []

    found_decorators = set()
    for node in ast.walk(tree):
        if hasattr(node, 'decorator_list'):
            for decorator in node.decorator_list:
                decorator_name = _get_decorator_name(decorator)
                if decorator_name:
                    found_decorators.add(decorator_name)

    missing_decorators = all_required_decorators - found_decorators
    for missing in sorted(list(missing_decorators)):
        errors.append(f"Decorador requerido '@{missing}' no encontrado en el archivo {filepath}")
        
    return errors

def _check_preserved_signatures(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]:
    """Validates that preserved symbols and their signatures have not changed."""
    errors = []
    expected_signatures_map = contract.preserved_signatures.get(filepath)
    if not expected_signatures_map:
        return []
    current_signatures_map = extract_ast_signatures(tree)
    for symbol_name, expected_sig in expected_signatures_map.items():
        if symbol_name not in current_signatures_map:
            errors.append(f"Símbolo preservado '{symbol_name}' fue eliminado del archivo {filepath}.")
        elif ' '.join(current_signatures_map.get(symbol_name, '').split()) != ' '.join(expected_sig.split()):
            errors.append(f"La firma del símbolo preservado '{symbol_name}' en {filepath} ha cambiado.\\n  Esperada: {expected_sig}\\n  Encontrada: {current_signatures_map.get(symbol_name)}")
    return errors

def _check_testing_techniques(tree: ast.AST, filepath: str, contract: AcceptanceContract, repo_context=None) -> list[str]:
    errors = []
    project_config = repo_context.structured_config if repo_context else None
    if not is_test_file(filepath, project_config=project_config):
        return errors
        
    used_techniques = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [arg.arg for arg in getattr(node.args, "args", [])]
            if "mocker" in args:
                used_techniques.add("pytest-mock")
            if "monkeypatch" in args:
                used_techniques.add("monkeypatch")
            
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "patch":
                        used_techniques.add("unittest.mock.patch")
                elif isinstance(decorator, ast.Attribute) and decorator.attr == "patch":
                    used_techniques.add("unittest.mock.patch")

        if isinstance(node, ast.Import):
            for name in node.names:
                if name.name == "pytest_mock":
                    used_techniques.add("pytest-mock")
        elif isinstance(node, ast.ImportFrom):
            if node.module == "unittest.mock":
                for name in node.names:
                    if name.name == "patch":
                        used_techniques.add("unittest.mock.patch")
                        
    required = {
        canonicalize_testing_technique(t)
        for t in contract.required_testing_techniques
    }

    forbidden = {
        canonicalize_testing_technique(t)
        for t in contract.forbidden_testing_techniques
    }
                        
    for req in required:
        if req not in used_techniques:
            errors.append(f"El archivo {filepath} no utiliza la técnica de testing requerida: {req}")
            
    for forb in forbidden:
        if forb in used_techniques:
            errors.append(f"El archivo {filepath} utiliza una técnica de testing prohibida: {forb}")
            
    return errors

def validate_contractual_ast(code: str, filepath: str, contract: AcceptanceContract, repo_context=None) -> list[str]:
    errors = []
    try:
        tree = ast.parse(code, filename=filepath)
    except SyntaxError as e:
        errors.append(f"Error de sintaxis en {filepath}: {e}")
        return errors

    normalized_path = filepath.replace("\\", "/")
    
    errors.extend(_check_forbidden_constructs(tree, normalized_path, contract))
    errors.extend(_check_exports(tree, normalized_path, contract))
    errors.extend(_check_tests(tree, normalized_path, contract, repo_context=repo_context))
    errors.extend(_check_imports(tree, normalized_path, contract))
    errors.extend(_check_patterns(tree, normalized_path, contract))
    errors.extend(_check_calls(tree, normalized_path, contract))
    errors.extend(_check_structures(tree, normalized_path, contract))
    errors.extend(_check_decorators(tree, normalized_path, contract))
    errors.extend(_check_preserved_signatures(tree, normalized_path, contract))
    errors.extend(_check_testing_techniques(tree, normalized_path, contract, repo_context=repo_context))
    
    return errors

def build_mypy_scope(generated_files: dict[str, str], repo_context: "RepositoryContext") -> list[str]:
    """Construye el conjunto de archivos Python a verificar con MyPy.
    Se parte de los archivos generados/modificados y se expande al cluster afectado:
    importers, dependencies, test covers, source targets.
    Filtros finales: solo ``.py``, sin ``vulture_whitelist.py``.
    """
    def _is_valid(p: str) -> bool:
        return p.endswith(".py") and "vulture_whitelist.py" not in p

    all_indices: dict = {**repo_context.source_index, **repo_context.test_index}
    scope: set[str] = set()
    for p in generated_files:
        if not _is_valid(p):
            continue
        scope.add(p)
        summary = all_indices.get(p)
        if summary:
            scope.update(c for c in summary.imported_by if _is_valid(c))
            scope.update(c for c in summary.imported_files if _is_valid(c))
            scope.update(c for c in summary.tested_by if _is_valid(c))
            scope.update(c for c in summary.tests_for if _is_valid(c))

    logging.info(f"MyPy scope calculado desde cluster afectado: {len(scope)} archivos.")
    return list(scope)

def run_mypy(filepaths: list[str], policy: "PythonQualityPolicy") -> tuple[bool, str]:
    logging.info(f"Ejecutando MyPy para {len(filepaths)} archivos (strict={policy.mypy_strict})...")
    try:
        mypy_args = [sys.executable, "-m", "mypy"]
        if policy.mypy_strict:
            mypy_args.append("--strict")
        mypy_args.extend(filepaths)

        result = subprocess.run(
            mypy_args,
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

    protected_test_files = set(contract.protected_tests.keys())
    deleted_protected_files = protected_test_files & deleted_files
    if deleted_protected_files:
        errors.append(f"El diseño elimina archivos que contienen tests protegidos: {sorted(deleted_protected_files)}")
    
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

def validate_generated_manifest(generated_files: dict[str, str], contract: AcceptanceContract, repo_context: RepositoryContext) -> tuple[bool, str]:
    required_changed_files = contract.required_new_files | contract.required_modified_files

    generated = {p.replace("\\", "/") for p in generated_files}
    missing = required_changed_files - generated

    if missing:
        return False, f"Faltan archivos que debían ser creados o modificados según el contrato: {sorted(missing)}"

    errors = []
    # Combine source and test indices to get all baseline hashes
    all_indices = {**repo_context.source_index, **repo_context.test_index}
    
    for path in contract.required_modified_files:
        if path in generated_files:
            current_hash = hashlib.sha256(
                generated_files[path].encode("utf-8")
            ).hexdigest()
            baseline = all_indices.get(path)
            baseline_hash = baseline.file_hash if baseline else None

            if not baseline_hash:
                errors.append(
                    f"MODIFY requerido pero '{path}' no existía en el baseline "
                    "(no se encontró en source_index ni test_index)."
                )
            elif current_hash == baseline_hash:
                errors.append(f"MODIFY requerido pero el contenido final es idéntico al estado inicial para: {path}")

    for path in contract.required_new_files:
        if path in generated_files:
            baseline = all_indices.get(path)
            if baseline:
                errors.append(f"CREATE requerido pero el archivo ya existía en el estado inicial: {path}")

    if errors:
        return False, "\n".join(errors)

    return True, ""

def validate_final_state(contract: AcceptanceContract) -> tuple[bool, str]:
    """
    Checks that all files required to exist at the end are present in the filesystem,
    and all deleted files are removed.
    """
    errors = []
    for path in contract.required_final_files:
        try:
            safe_path = resolve_safe_path(".", path)
            if not os.path.exists(safe_path):
                errors.append(f"El archivo final requerido '{path}' no existe en el sistema de archivos.")
        except ValueError as e:
            errors.append(str(e))
            
    for path in contract.required_deleted_files:
        try:
            safe_path = resolve_safe_path(".", path)
            if os.path.exists(safe_path):
                errors.append(f"El archivo que debía eliminarse todavía existe: {path}")
        except ValueError as e:
            errors.append(str(e))
    
    if errors:
        return False, "\n".join(errors)
    
    return True, ""

def _derive_gate_plan(repo_context: RepositoryContext, contract: AcceptanceContract) -> "QualityGatePlan":
    """Deriva el plan de ejecución de Quality Gates a partir del contexto estructurado."""
    plan = QualityGatePlan()
    
    # 1. Detección por dependencias y configuración (Usando structured_config)
    cfg = repo_context.structured_config
    if cfg.mypy_enabled:
        plan.run_mypy = True
    if cfg.ruff_enabled:
        plan.run_ruff = True
    if cfg.vulture_enabled:
        plan.run_vulture = True

    # 3. Normalizar las reglas contractuales
    required_tools = {tool.lower() for tool in contract.required_quality_tools}
    forbidden_tools = {tool.lower() for tool in contract.forbidden_quality_tools}
    tests_contracted = bool(
        contract.required_tests
        or contract.protected_tests
        or contract.required_testing_techniques
    )
    
    repo_framework = repo_context.detected_test_framework
    if repo_framework is None and "pytest" in cfg.detected_quality_tools:
        repo_framework = "pytest"

    QUALITY_TOOL_MAP = {
        "mypy": "run_mypy",
        "ruff": "run_ruff",
        "vulture": "run_vulture",
    }

    for tool in required_tools:
        attr = QUALITY_TOOL_MAP.get(tool)
        if attr:
            setattr(plan, attr, True)

    for tool in forbidden_tools:
        attr = QUALITY_TOOL_MAP.get(tool)
        if attr:
            setattr(plan, attr, False)

    explicit_framework = None
    if "pytest" in required_tools:
        explicit_framework = "pytest"
    elif "unittest" in required_tools:
        explicit_framework = "unittest"

    required_techniques = {
        canonicalize_testing_technique(t)
        for t in contract.required_testing_techniques
    }
    
    implied_framework = None
    pytest_only_techniques = {
        "pytest-mock",
        "monkeypatch",
    }
    
    if required_techniques & pytest_only_techniques:
        implied_framework = "pytest"
        
    if implied_framework in forbidden_tools:
        raise PreflightError(
            f"El contrato exige técnicas que requieren "
            f"'{implied_framework}', pero ese framework está prohibido."
        )

    if explicit_framework:
        resolved_framework = explicit_framework
    elif implied_framework:
        resolved_framework = implied_framework
    elif repo_framework in {"pytest", "unittest"} and repo_framework not in forbidden_tools:
        resolved_framework = repo_framework
    else:
        resolved_framework = "none"

    plan.test_framework = resolved_framework

    # Decidir run_tests después de resolver el framework
    if explicit_framework:
        plan.run_tests = True
    elif tests_contracted:
        if plan.test_framework == "none":
            raise PreflightError(
                "El contrato exige pruebas pero no existe "
                "un framework permitido para ejecutarlas."
            )
        plan.run_tests = True
    elif plan.test_framework != "none":
        # Mantener regresión normal del repositorio
        plan.run_tests = True
    else:
        plan.run_tests = False

    # Invariantes y validación final de frameworks
    if plan.run_tests:
        if plan.test_framework not in {"pytest", "unittest"}:
            raise PreflightError("run_tests=True sin framework de testing válido.")
    else:
        plan.test_framework = "none"

    logging.info(f"Plan de Quality Gates derivado: {plan.model_dump_json()}")
    return plan

def validate_testing_policy_compatibility(
    framework: Literal["pytest", "unittest", "none"],
    contract: AcceptanceContract,
) -> list[str]:
    errors = []

    required = {
        canonicalize_testing_technique(t)
        for t in contract.required_testing_techniques
    }

    if framework == "unittest":
        incompatible = required & {
            "pytest-mock",
            "monkeypatch",
        }

        if incompatible:
            errors.append(
                "Framework unittest incompatible con técnicas "
                f"obligatorias: {sorted(incompatible)}"
            )

    if required and framework == "none":
        errors.append(
            "Hay técnicas de testing obligatorias pero no existe "
            "un framework de testing resuelto."
        )

    return errors

def resolve_safe_path(root: str, relative_path: str) -> str:
    root_abs = os.path.abspath(root)
    target_abs = os.path.abspath(os.path.join(root_abs, relative_path))

    if os.path.commonpath([root_abs, target_abs]) != root_abs:
        raise ValueError(f"Ruta fuera del repositorio: {relative_path}")

    return target_abs

# =====================================================================
# FASES DEL PIPELINE DE ARQUITECTURA EVOLUTIVA
# =====================================================================
def fetch_issue(issue_id: int, repo) -> tuple[str, str]:
    logging.info(f"Leyendo requisitos en el Issue #{issue_id}...")
    issue = repo.get_issue(number=issue_id)
    return issue.title, issue.body

def agent_analyze_and_design(title: str, description: str, contract: AcceptanceContract, repo_context: RepositoryContext, runtime: RuntimeClients, context_manager: "RepositoryContextManager", design_feedback: str = "") -> dict:
    """Diseña la solucion tecnica usando un PromptBudget con prioridades fail-closed/warn-and-truncate."""
    MAX_INPUT = 130000
    RESERVED_OUTPUT = 8192
    budget = PromptBudget(max_input_tokens=MAX_INPUT, reserved_output_tokens=RESERVED_OUTPUT)

    # ----- FUENTES OBLIGATORIAS (fail-closed si no caben) -----
    # 1. AcceptanceContract
    contract_json = contract.model_dump_json(indent=2)
    contract_tokens = len(contract_json) // 4
    if not budget.can_add(contract_tokens):
        raise PreflightError(
            f"El AcceptanceContract ({contract_tokens} tokens) supera el presupuesto disponible "
            f"({budget.remaining} tokens). No se puede proceder."
        )
    budget.add(contract_tokens)

    # 2. Issue (title + description)
    issue_text = f"Titulo: {title}\nRequisitos: {description}"
    issue_tokens = len(issue_text) // 4
    if not budget.can_add(issue_tokens):
        raise PreflightError(
            f"El Issue ({issue_tokens} tokens) supera el presupuesto disponible tras el contrato. "
            "No se puede proceder."
        )
    budget.add(issue_tokens)

    # 3. Instrucciones fijas minimas del prompt
    FIXED_PROMPT_TOKENS = 1200
    if not budget.can_add(FIXED_PROMPT_TOKENS):
        raise PreflightError(
            "Las instrucciones fijas del arquitecto no caben en el presupuesto. "
            "El prompt esta sobrecargado con contrato + issue."
        )
    budget.add(FIXED_PROMPT_TOKENS)

    # ----- FUENTES OPCIONALES (warn-and-truncate) -----
    # 4. architecture_document
    arch_doc_raw = repo_context.architecture_document or "[No se encontro documento de arquitectura.]"
    ARCH_MAX = 8000
    arch_tok = len(arch_doc_raw) // 4
    if arch_tok > ARCH_MAX:
        arch_doc_display = arch_doc_raw[:ARCH_MAX * 4] + "\n... [ARQUITECTURA TRUNCADA]"
        logging.warning(f"agent_analyze_and_design: architecture_document truncado a {ARCH_MAX} tokens.")
        arch_tok = ARCH_MAX
    else:
        arch_doc_display = arch_doc_raw
    if budget.can_add(arch_tok):
        budget.add(arch_tok)
    else:
        arch_doc_display = "[arquitectura omitida por presupuesto]"
        logging.warning("agent_analyze_and_design: architecture_document omitido por presupuesto.")

    # 5. structured_config
    project_config_json = repo_context.structured_config.model_dump_json(indent=2)
    pcfg_tok = len(project_config_json) // 4
    if not budget.can_add(pcfg_tok):
        project_config_json = "[config omitida por presupuesto]"
        logging.warning("agent_analyze_and_design: project_config omitida por presupuesto.")
    else:
        budget.add(pcfg_tok)

    # 6. architecture_conflicts
    arch_conflicts_json = json.dumps([c.model_dump() for c in repo_context.architecture_conflicts], indent=2)
    aconf_tok = len(arch_conflicts_json) // 4
    if not budget.can_add(aconf_tok):
        arch_conflicts_display = "[conflictos omitidos por presupuesto]"
        logging.warning("agent_analyze_and_design: architecture_conflicts omitidos por presupuesto.")
    else:
        budget.add(aconf_tok)
        arch_conflicts_display = arch_conflicts_json if repo_context.architecture_conflicts else "[No se detectaron conflictos.]"

    # 7. repository_map
    repo_map = repo_context.repository_map or "[Repositorio limpio]"
    map_tok = len(repo_map) // 4
    REPO_MAP_MAX = 12000
    if map_tok > REPO_MAP_MAX:
        repo_map = repo_map[:REPO_MAP_MAX * 4] + "\n... [MAPA TRUNCADO]"
        map_tok = REPO_MAP_MAX
        logging.warning(f"agent_analyze_and_design: repository_map truncado a {REPO_MAP_MAX} tokens.")
    if budget.can_add(map_tok):
        budget.add(map_tok)
    else:
        repo_map = "[mapa omitido por presupuesto]"
        logging.warning("agent_analyze_and_design: repository_map omitido por presupuesto.")

    # 8. relevant files
    omitted_files = []
    relevant_files_context = ""
    if repo_context.relevant_source_files or repo_context.relevant_test_files:
        relevant_files_context += "\n\nCONTENIDO DE ARCHIVOS RELEVANTES (PRE-SELECCIONADOS POR RELEVANCIA):\n"
        for path, file_content in {**repo_context.relevant_source_files, **repo_context.relevant_test_files}.items():
            frag = f"--- INICIO {path} ---\n{file_content}\n--- FIN {path} ---\n"
            tok = len(frag) // 4
            if budget.can_add(tok):
                relevant_files_context += frag
                budget.add(tok)
            else:
                relevant_files_context += f"[{path}: omitido por presupuesto]\n"
                omitted_files.append(path)
                logging.warning(f"agent_analyze_and_design: archivo relevante '{path}' omitido por presupuesto.")

    # 9. design_feedback
    feedback_section = ""
    if design_feedback:
        fb_tok = len(design_feedback) // 4
        if budget.can_add(fb_tok):
            feedback_section = f"FEEDBACK DEL DISENO ANTERIOR (DEBES CORREGIR ESTO):\n{design_feedback}"
            budget.add(fb_tok)
        else:
            logging.warning("agent_analyze_and_design: design_feedback omitido por presupuesto.")

    if omitted_files:
        logging.warning(f"agent_analyze_and_design: {len(omitted_files)} archivos relevantes omitidos: {omitted_files}")

    prompt = f"""
    Actuas como el Arquitecto de Software Principal. Tu objetivo es disenar una solucion tecnica estructurada, elegante, testable y lista para produccion que cumpla con la especificacion del Issue.

    Para entender el sistema, tienes varias fuentes de informacion clave:
    1. CONTRATO DE ACEPTACION: Las reglas estrictas y deterministas que tu diseno DEBE cumplir. Es tu principal restriccion.
    2. DOCUMENTO DE ARQUITECTURA: Describe la vision y restricciones del sistema. CUIDADO: puede estar desactualizado.
    3. CONFLICTOS DE ARQUITECTURA: Analisis automatico de posibles desactualizaciones.
    4. INDICES AST: Fuente de verdad sobre el estado actual del codigo (el mapa del repositorio).
    5. CONTENIDO DE ARCHIVOS RELEVANTES: El contenido completo de los archivos mas importantes.

    CONTRATO DE ACEPTACION (REGLAS OBLIGATORIAS PARA TU DISENO):
    --- INICIO CONTRATO ---
    {contract_json}
    --- FIN CONTRATO ---

    CONFLICTOS DETECTADOS ENTRE ARQUITECTURA Y CODIGO REAL:
    --- INICIO CONFLICTOS ---
    {arch_conflicts_display}
    --- FIN CONFLICTOS ---

    DOCUMENTO DE ARQUITECTURA:
    --- INICIO DOCUMENTO ---
    {arch_doc_display}
    --- FIN DOCUMENTO ---

    CONFIGURACION DEL PROYECTO (Reglas de linters, dependencias base):
    --- INICIO CONFIGURACION ---
    {project_config_json}
    --- FIN CONFIGURACION ---

    {relevant_files_context}

    ESPECIFICACION FUNCIONAL DEL ISSUE:
    - {issue_text}

    {feedback_section}

    TOPOLOGIA EN DISCO ACTUAL Y FIRMAS AST:
    --- INICIO MAPA ---
    {repo_map}
    --- FIN MAPA ---

    REGLAS DE RECONCILIACION Y TOPOLOGIA:
    - ALINEACION ESTRICTA: Reconcilia los requerimientos funcionales con la TOPOLOGIA EN DISCO ACTUAL. Utiliza obligatoriamente las clases y metodos existentes.
    - INSPECCION DE FIRMAS OBLIGATORIA: Examina meticulosamente el mapa (AST) adjunto para ver si el metodo '__init__' de las clases objetivo declara parametros. Queda terminantemente PROHIBIDO pasar parametros con nombre (kwargs) si la estructura no coincide con la firma real dictada por el mapa.
    - EXPORTACION EXPLICITA (__all__): Si el AcceptanceContract especifica required_exports para un archivo, tu diseno debe instruir su creacion.

    EXPANSION DE CONTEXTO BAJO DEMANDA:
    - Si necesitas examinar el codigo de OTRO archivo, devuelve is_context_request: true y rellena context_request. NO generes el diseno en ese paso.
    """

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=ProjectDesign,
        temperature=0.1
    )
    ensure_prompt_fits(prompt, budget, "Technical Design")
    response = runtime.ai_client.models.generate_content(model=MODEL_HEAVY, contents=prompt, config=config)
    return json.loads(response.text or "{}")


def estimate_repository_context_tokens(repo_context: RepositoryContext, issue_description: str, contract: AcceptanceContract | None = None) -> int:
    toks = 2000 # fixed overhead
    toks += len(issue_description) // 4
    if contract:
        toks += len(contract.model_dump_json()) // 4
    
    if repo_context.architecture_document:
        toks += len(repo_context.architecture_document) // 4
    
    toks += sum(len(c) // 4 for c in repo_context.project_configuration.values())
    
    if hasattr(repo_context, 'structured_config') and repo_context.structured_config:
        toks += len(repo_context.structured_config.model_dump_json()) // 4
        
    if hasattr(repo_context, 'quality_policy') and repo_context.quality_policy:
        toks += len(repo_context.quality_policy.model_dump_json()) // 4
    
    for c in repo_context.relevant_source_files.values(): toks += len(c) // 4
    for c in repo_context.relevant_test_files.values(): toks += len(c) // 4
    for c in repo_context.dependency_files.values(): toks += len(c) // 4
    if repo_context.repository_map:
        toks += len(repo_context.repository_map) // 4
        
    return toks

class PromptContextBuilder:
    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return len(text) // 4

    @staticmethod
    def build_for_coder(action: dict, design: dict, generated_so_far: dict[str, str], repo_context: RepositoryContext, context_manager: "RepositoryContextManager", budget: PromptBudget) -> PromptPayload:
        filepath = action['filepath']
        content = ""
        omitted = []
        
        def try_add(frag: str, path_ref: str):
            nonlocal content
            tok = PromptContextBuilder._estimate_tokens(frag)
            if budget.can_add(tok):
                content += frag
                budget.add(tok)
            else:
                omitted.append(path_ref)

        for dep in design.get("dependencies", []):
            code_text = context_manager.get_file_content(dep)
            try_add(f"\n\n# Dependencia ('{dep}'):\n{code_text}", dep)
            
        for p, code_text in generated_so_far.items():
            if p != filepath:
                try_add(f"\n\n# Previamente generado ('{p}'):\n{code_text}", p)
                
        summary = repo_context.source_index.get(filepath) or repo_context.test_index.get(filepath)
        if summary:
            for dep in summary.imported_files:
                if dep not in generated_so_far and dep not in design.get("dependencies", []):
                    code_text = context_manager.get_file_content(dep)
                    try_add(f"\n\n# Contexto importado ('{dep}'):\n{code_text}", dep)
                    
        return PromptPayload(content=content, estimated_tokens=budget.used_tokens, omitted_files=omitted)

    @staticmethod
    def build_for_tests(action: dict, generated_so_far: dict[str, str], repo_context: RepositoryContext, context_manager: "RepositoryContextManager", budget: PromptBudget) -> PromptPayload:
        filepath = action['filepath']
        content = ""
        omitted = []
        
        def try_add(frag: str, path_ref: str):
            nonlocal content
            tok = PromptContextBuilder._estimate_tokens(frag)
            if budget.can_add(tok):
                content += frag
                budget.add(tok)
            else:
                omitted.append(path_ref)

        prod_files = [p for p in generated_so_far if not is_test_file(p, project_config=repo_context.structured_config)]
        for p in prod_files:
            try_add(f"\n\n# Archivo de Producción ('{p}'):\n{generated_so_far[p]}", p)
            
        summary = repo_context.test_index.get(filepath)
        if summary:
            for source_path in summary.tests_for:
                if source_path not in prod_files:
                    code_text = context_manager.get_file_content(source_path)
                    try_add(f"\n\n# Objetivo de Test ('{source_path}'):\n{code_text}", source_path)
                    
        return PromptPayload(content=content, estimated_tokens=budget.used_tokens, omitted_files=omitted)

    @staticmethod
    def build_for_reviewer(generated_files: dict[str, str], max_tokens: int = 100000) -> list[PromptPayload]:
        payloads = []
        content = ""
        current_tokens = 0
        for path, code_text in generated_files.items():
            frag = f"\n\n### Archivo: `{path}`\n```python\n{code_text}\n```\n"
            tok = PromptContextBuilder._estimate_tokens(frag)
            
            if tok > max_tokens:
                raise PreflightError(f"El archivo '{path}' excede el tamaño máximo de un lote ({max_tokens} tokens).")
                
            if current_tokens + tok > max_tokens and content:
                payloads.append(PromptPayload(content=content, estimated_tokens=current_tokens))
                content = ""
                current_tokens = 0
            content += frag
            current_tokens += tok
        if content:
            payloads.append(PromptPayload(content=content, estimated_tokens=current_tokens))
        return payloads

    @staticmethod
    def build_for_audit(generated_files: dict[str, str], max_tokens: int = 100000) -> list[PromptPayload]:
        payloads = []
        content = ""
        current_tokens = 0
        for path, code_text in generated_files.items():
            frag = f"\n\nArchivo: '{path}'\n```python\n{code_text}\n```\n"
            tok = PromptContextBuilder._estimate_tokens(frag)
            
            if tok > max_tokens:
                raise PreflightError(f"El archivo '{path}' excede el tamaño máximo de un lote ({max_tokens} tokens).")
                
            if current_tokens + tok > max_tokens and content:
                payloads.append(PromptPayload(content=content, estimated_tokens=current_tokens))
                content = ""
                current_tokens = 0
            content += frag
            current_tokens += tok
        if content:
            payloads.append(PromptPayload(content=content, estimated_tokens=current_tokens))
        return payloads
        
    @staticmethod
    def build_for_report(generated_files: dict[str, str], budget: PromptBudget) -> PromptPayload:
        content = ""
        omitted = []
        for path, code_text in generated_files.items():
            frag = f"\n\n### Archivo: `{path}`\n```python\n{code_text}\n```\n"
            tok = PromptContextBuilder._estimate_tokens(frag)
            if budget.can_add(tok):
                content += frag
                budget.add(tok)
            else:
                omitted.append(path)
        return PromptPayload(content=content, estimated_tokens=budget.used_tokens, omitted_files=omitted)
        
    @staticmethod
    def build_for_docs(design: dict, generated_files: dict[str, str], budget: PromptBudget) -> PromptPayload:
        content = ""
        omitted = []
        for path, code_text in generated_files.items():
            frag = f"\n\n### Modificación: `{path}`\n```python\n{code_text}\n```\n"
            tok = PromptContextBuilder._estimate_tokens(frag)
            if budget.can_add(tok):
                content += frag
                budget.add(tok)
            else:
                omitted.append(path)
        return PromptPayload(content=content, estimated_tokens=budget.used_tokens, omitted_files=omitted)


def agent_implement_code(action: dict, file_contract: FileContract, design: dict, generated_so_far: dict[str, str], repo_context: RepositoryContext, runtime: RuntimeClients, context_manager: "RepositoryContextManager", feedback: str = "") -> str:
    logging.info(f"Procesando '{action['filepath']}' | Operacion: {action['operation']} con {MODEL_LIGHT}...")
    budget = PromptBudget(max_input_tokens=100000, reserved_output_tokens=8000)
    
    # Priority 1: Instrucciones fijas del agente / wrapper obligatorio
    fixed_instructions = """
    Actuas como un Software Engineer.
    
    Tus directrices y prioridades son claras:
    - El FileContract es OBLIGATORIO y prevalece frente a instrucciones inferiores.
    - Debes devolver el contenido COMPLETO final del archivo, sin explicaciones adicionales fuera del bloque de codigo.
    - Si la operacion es MODIFY, parte del codigo existente provisto y preserva todo el comportamiento no afectado por el cambio.
    
    FileContract: 
    Action: 
    Codigo Actual: 
    Feedback: 
    Contexto Dinamico: 
    Dependencias y Generados: 
    """
    fixed_toks = len(fixed_instructions) // 4
    if not budget.can_add(fixed_toks):
        raise PreflightError("Instrucciones fijas exceden el presupuesto del Coder.")
    budget.add(fixed_toks)
    
    # Priority 2: FileContract
    file_contract_json = file_contract.model_dump_json(indent=2)
    p2_toks = len(file_contract_json) // 4
    if not budget.can_add(p2_toks):
        raise PreflightError("FileContract excede el presupuesto del Coder.")
    budget.add(p2_toks)
    
    # Priority 3: Action details
    action_str = f"filepath: {action.get('filepath')}\noperation: {action.get('operation')}\nsignatures: {action.get('signatures')}\ninstructions: {action.get('instructions')}"
    p3_toks = len(action_str) // 4
    if not budget.can_add(p3_toks):
        raise PreflightError("La instruccion de accion excede el presupuesto del Coder.")
    budget.add(p3_toks)
    
    # Priority 4: Existing code (if MODIFY)
    existing_code = ""
    filepath = action.get('filepath')
    if action.get('operation') == 'MODIFY':
        existing_code = context_manager.get_file_content(action["filepath"])
        p4_toks = len(existing_code) // 4
        if not budget.can_add(p4_toks):
            raise PreflightError(f"El codigo existente de {filepath} excede el presupuesto del Coder.")
        budget.add(p4_toks)
        
    # Priority 5: Feedback
    p5_toks = len(feedback) // 4
    if not budget.can_add(p5_toks):
        feedback = feedback[:budget.remaining * 4]
        logging.warning("Feedback truncado en Coder.")
    if feedback:
        budget.add(len(feedback) // 4)
    
    # Priority 6: Dynamic Context (from Architect)
    context_str = json.dumps(design.get('context', {}))
    p6_toks = len(context_str) // 4
    if budget.can_add(p6_toks):
        budget.add(p6_toks)
    else:
        context_str = "{}"
        
    # Priority 7: Dependencies and Generated
    # We use build_for_coder which we assume respects budget.remaining
    # For simplicity, we just pass budget.remaining to build_for_coder
    payload = PromptContextBuilder.build_for_coder(action, design, generated_so_far, repo_context, context_manager, budget)
    dep_gen_str = payload.content
    
    prompt = f"""
    Actuas como un Software Engineer.
    
    Tus directrices y prioridades son claras:
    - El FileContract es OBLIGATORIO y prevalece frente a instrucciones inferiores.
    - Debes devolver el contenido COMPLETO final del archivo, sin explicaciones adicionales fuera del bloque de codigo.
    - Si la operacion es MODIFY, parte del codigo existente provisto y preserva todo el comportamiento no afectado por el cambio.
    
    FileContract: {file_contract_json}
    Action: {action_str}
    Codigo Actual: {existing_code}
    Feedback: {feedback}
    Contexto Dinamico: {context_str}
    Dependencias y Generados: {dep_gen_str}
    """
    
    ensure_prompt_fits(prompt, budget, "Coder")
    import os
    _, ext = os.path.splitext(action["filepath"])
    LANGUAGE_BY_EXTENSION = {
        ".py": "python", ".json": "json", ".ini": "ini",
        ".cfg": "ini", ".toml": "toml", ".yaml": "yaml",
        ".yml": "yaml", ".md": "markdown"
    }
    response = runtime.ai_client.models.generate_content(
        model=MODEL_LIGHT,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
        ),
    )
    
    return extract_code(response.text or "", LANGUAGE_BY_EXTENSION.get(ext))

def resolve_mocking_instruction(framework: Literal["pytest", "unittest"], file_contract: FileContract, repo_context: RepositoryContext) -> str:
    forbidden = {
        canonicalize_testing_technique(t)
        for t in file_contract.forbidden_testing_techniques
    }
    required = {
        canonicalize_testing_technique(t)
        for t in file_contract.required_testing_techniques
    }
    
    if framework == "unittest":
        if "unittest.mock.patch" in forbidden:
            return "Usa las utilidades estándar de unittest permitidas por el contrato sin aplicar técnicas prohibidas."
        return "Usa unittest.mock.patch para aislar dependencias."
    
    if required:
        if "pytest-mock" in required:
            return "Usa pytest-mock mediante el fixture mocker."
        if "monkeypatch" in required:
            return "Usa el fixture monkeypatch."
        if "unittest.mock.patch" in required:
            return "Usa unittest.mock.patch dentro de la suite pytest."
    
    candidates = []
    if "pytest-mock" not in forbidden:
        candidates.append("pytest-mock mediante el fixture mocker")
    
    if "monkeypatch" not in forbidden:
        candidates.append("el fixture monkeypatch")
        
    if candidates:
        return f"Usa {' o '.join(candidates)} para aislar dependencias."
        
    return (
        "Usa pytest respetando el contrato, sin pytest-mock, "
        "mocker ni monkeypatch."
    )

def agent_generate_tests(action: dict, file_contract: FileContract, generated_so_far: dict[str, str], issue_desc: str, repo_context: RepositoryContext, framework: Literal["pytest", "unittest"], runtime: RuntimeClients, context_manager: "RepositoryContextManager", feedback: str = "") -> str:
    logging.info(f"Disenando suite de pruebas unitarias para '{action['filepath']}'...")

    budget = PromptBudget(max_input_tokens=128000, reserved_output_tokens=8192)

    # Priority 1: Issue
    add_required_or_fail(budget, issue_desc, "Issue desc en Test Generator")
    
    # Priority 2: FileContract
    file_contract_json = file_contract.model_dump_json(indent=2)
    add_required_or_fail(budget, file_contract_json, "FileContract en Test Generator")
    
    # Priority 3: framework
    add_required_or_fail(budget, framework, "Framework")
    
    # Priority 4: filepath/operation
    add_required_or_fail(budget, action['filepath'] + action['operation'], "Filepath/Operation")
    
    # Priority 5: signatures
    add_required_or_fail(budget, action.get("signatures", ""), "Signatures")
    
    # Priority 6: instructions
    add_required_or_fail(budget, action.get("instructions", ""), "Instructions")
    
    # Priority 7, 8, 9: mocking, typing, exports
    mocking_instruction = resolve_mocking_instruction(framework, file_contract, repo_context)
    if repo_context.quality_policy.require_argument_annotations:
        typing_instruction = "2. TIPADO ESTRICTO OBLIGATORIO: Todas las funciones de test y los argumentos (incluyendo los mocks inyectados por `@patch`) deben tener type hints (ej. `def test_algo(mock_obj: Mock) -> None:`)."
    else:
        typing_instruction = "2. TIPADO FLEXIBLE: Respeta la convención de tipado existente en los tests (no exijas type hints si no son prevalentes)."

    if repo_context.quality_policy.require_explicit_exports or file_contract.required_exports:
        exports_instruction = "3. TESTEO EXHAUSTIVO DE INTERFACES PÚBLICAS: Es obligatorio importar, instanciar y usar explícitamente todas las clases o funciones declaradas en la variable '__all__' del archivo de producción objetivo para reducir la tasa de código muerto de Vulture a 0%."
    else:
        exports_instruction = "3. TESTEO ENFOCADO: Evalúa el contrato y los requerimientos sin obligatoriedad de referenciar __all__."

    add_required_or_fail(budget, mocking_instruction + typing_instruction + exports_instruction, "Reglas de test")
    
    # Priority 10: existing_test_code (si MODIFY)
    existing_test_code = ""
    if action["operation"].upper() == "MODIFY":
        existing_test_code = context_manager.get_file_content(action["filepath"])
        add_required_or_fail(budget, existing_test_code, "Existing Test Code")
        
    # Priority 11: fixed instructions
    add_required_or_fail(budget, "Escribe una suite de pruebas unitarias exhaustiva con framework para validar el archivo: REQUISITOS ORIGINALES DEL ISSUE (FUENTE DE VERDAD SUPERIOR): CONTRATO DE ARCHIVO (REGLAS OBLIGATORIAS PARA ESTE ARCHIVO DE TEST): FIRMAS PROPUESTAS POR EL ARQUITECTO: INSTRUCCIONES ESPECÍFICAS DEL ARCHIVO: Las instrucciones del arquitecto están subordinadas al Issue original y al Contrato. Si existe una contradicción, prevalece el Contrato. CONTEXTO DINÁMICO RELEVANTE: ESTÁNDARES DE DISEÑO DE TESTING INDUSTRIAL: INDEPENDENCIA Y AISLAMIENTO: Devuelve UNICAMENTE el codigo en un bloque markdown", "Instrucciones fijas")
    
    # Priority: feedback
    if feedback:
        if not budget.can_add(len(feedback) // 4):
            feedback = feedback[:budget.remaining * 4]
            logging.warning("Feedback truncado en Test Generator.")
        budget.add(len(feedback) // 4)
    
    # Priority: Contexto Dinámico
    payload = PromptContextBuilder.build_for_tests(action, generated_so_far, repo_context, context_manager, budget)
    contexto_dinamico = payload.content

    prompt = f"""
    Escribe una suite de pruebas unitarias exhaustiva con '{framework}' para validar el archivo: '{action['filepath']}'

    REQUISITOS ORIGINALES DEL ISSUE (FUENTE DE VERDAD SUPERIOR):
    {issue_desc}

    📜 CONTRATO DE ARCHIVO (REGLAS OBLIGATORIAS PARA ESTE ARCHIVO DE TEST):
    {file_contract_json}

    FIRMAS PROPUESTAS POR EL ARQUITECTO:
    {action["signatures"]}

    INSTRUCCIONES ESPECÍFICAS DEL ARCHIVO:
    {action["instructions"]}

    Las instrucciones del arquitecto están subordinadas al Issue original y al Contrato.
    Si existe una contradicción, prevalece el Contrato.

    CONTEXTO DINÁMICO RELEVANTE:
    {contexto_dinamico}

    📜 ESTÁNDARES DE DISEÑO DE TESTING INDUSTRIAL:
    1. INDEPENDENCIA Y AISLAMIENTO: {mocking_instruction}
    {typing_instruction}
    {exports_instruction}

    {'FEEDBACK DEL INTENTO ANTERIOR (DEBES CORREGIR ESTO):' + feedback if feedback else ''}

    {f'''
    CÓDIGO DE TEST EXISTENTE (OPERACIÓN MODIFY):
    El siguiente código ya existe en el archivo. Debes preservarlo, corregirlo si el feedback lo indica, y añadir nuevas pruebas para los nuevos requisitos. No elimines pruebas existentes que no estén relacionadas con el feedback.
    ---
    {existing_test_code}
    ---
    ''' if existing_test_code else ''}

    Devuelve UNICAMENTE el codigo de '{framework}' en un bloque markdown usando {MD_FENCE}python.
    """
    ensure_prompt_fits(prompt, budget, "Test Generator")
    response = runtime.ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt, config=types.GenerateContentConfig(temperature=0.0))
    return extract_code(response.text, "python")

def run_local_tests(test_filename: str, framework: str = "pytest") -> tuple[bool, str]:
    logging.info(f"Ejecutando {framework} para {test_filename}...")
    try:
        if framework.lower() == "unittest":
            # For unittest we can run python -m unittest <file>
            result = subprocess.run([sys.executable, "-m", "unittest", "-v", test_filename], capture_output=True, text=True, timeout=600)
        else:
            result = subprocess.run([sys.executable, "-m", "pytest", "-v", test_filename], capture_output=True, text=True, timeout=600)
        return result.returncode == 0, result.stdout + "\n" + result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        error_message = f"Fallo de infraestructura al ejecutar {framework}: {e}. Asegúrate de que {framework} está instalado y el entorno es correcto."
        logging.error(error_message)
        return False, error_message


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
    
    # Priority 1: Issue/title
    add_required_or_fail(budget, title, "Issue/title")
    
    # Priority 2: architecture_justification
    architecture_justification = design.get("architecture_justification", "[no disponible]")
    add_required_or_fail(budget, architecture_justification, "Architecture Justification")
    
    # Priority 3: fixed instructions
    fixed_instructions = "Actúas como un ingeniero de release. Genera un reporte Markdown detallado del ciclo de ejecución. Incluye el título, la justificación de la arquitectura, resumen de dependencias/archivos modificados, resumen de calidad estática, y análisis de fallos en tests si los hay."
    add_required_or_fail(budget, fixed_instructions, "Fixed Instructions")
    
    # Priority 4: resumen de tests fallidos/errores
    lines = pytest_log.split('\n')
    important_failures = [l for l in lines if 'FAILED' in l or 'ERROR' in l]
    important_tracebacks = [l for l in lines if 'Traceback' in l]
    
    test_summary_parts = []
    
    # 1. FAILED / ERROR representativos
    failures_str = "\n".join(important_failures)
    if not budget.can_add(len(failures_str) // 4):
        failures_str = failures_str[:max(0, budget.remaining * 4 - 100)] + "\n... [TRUNCADO FALLOS]"
    if failures_str:
        budget.add(len(failures_str) // 4)
        test_summary_parts.append(failures_str)
        
    # 2. tracebacks relacionados
    tb_str = "\n".join(important_tracebacks)
    if tb_str and budget.remaining > 0:
        if not budget.can_add(len(tb_str) // 4):
            tb_str = tb_str[:max(0, budget.remaining * 4 - 100)] + "\n... [TRUNCADO TRACEBACKS]"
        budget.add(len(tb_str) // 4)
        test_summary_parts.append(tb_str)
        
    test_summary = "\n".join(test_summary_parts)
    
    # Priority 5: resumen Security/SAST
    # Ensure SAST doesn't blow up if it's somehow huge, though normally it's small. We'll add_required_or_fail or truncate.
    if not budget.can_add(len(sast_report) // 4):
        sast_report = sast_report[:budget.remaining * 4]
    budget.add(len(sast_report) // 4)
    
    # Priority 6: manifest
    manifest_str = str(list(generated_files.keys()))
    add_required_or_fail(budget, manifest_str, "Manifest")
    
    # Priority 7: contenido real de generated_files que quepa
    payload = PromptContextBuilder.build_for_report(generated_files, budget)
    content_str = payload.content
    
    # Priority 8: resto de logs
    resto_logs = "\n".join(lines[-50:])
    if resto_logs and budget.remaining > 0:
        if not budget.can_add(len(resto_logs) // 4):
            resto_logs = resto_logs[-budget.remaining * 4:]
        budget.add(len(resto_logs) // 4)
    else:
        resto_logs = ""
    
    prompt = f"""
    {fixed_instructions}
    
    Title/Issue: {title}
    Architecture Justification: {architecture_justification}
    SAST: {sast_report}
    Generated Files Manifest: {manifest_str}
    
    Content of generated files:
    {content_str}
    
    Test Failures/Errors:
    {test_summary}
    
    Test Tail Logs:
    {resto_logs}
    """
    
    ensure_prompt_fits(prompt, budget, "Execution Report")
    response = runtime.ai_client.models.generate_content(model=MODEL_LIGHT, contents=prompt)
    os.makedirs("docs/reports", exist_ok=True)
    report_path = f"docs/reports/run_issue_{issue_id}.md"
    with open(report_path, "w", encoding="utf-8") as f: f.write((response.text or "").strip())
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

    # Priority 2: Git Diff
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

    # Priority 3: Manifest
    manifest_text = repr(list(generated_files.keys()))
    if not budget.can_add(len(manifest_text) // 4):
        manifest_text = "[Manifiesto omitido]"
    else:
        budget.add(len(manifest_text) // 4)
        
    # Priority 4: Gate Summary
    gate_summary = repr([{"name": g.name, "passed": g.passed, "executed": g.executed} for g in gate_results])
    if not budget.can_add(len(gate_summary) // 4):
        gate_summary = "[Gate summary omitido]"
    else:
        budget.add(len(gate_summary) // 4)

    # Priority 5: Issue
    meta = f"Issue: #{issue_id} - {title}\nDescripcion: {description}"
    if not budget.can_add(len(meta) // 4):
        meta = "[Issue omitido]"
    else:
        budget.add(len(meta) // 4)

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
        full_path = os.path.join(repo_context.repository_map.get("root", "."), arch_file)
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
    
    # Priority 1: Instrucciones de gobernanza
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
    add_required_or_fail(budget, gobernanza, "Gobernanza Post-Mortem")
    
    # Priority 2: Contexto del Issue
    issue_ctx = f"Issue #{issue_id}: '{title}' | Spec: {description}"
    add_required_or_fail(budget, issue_ctx, "Issue en Post-Mortem")
    
    failed_gates = [g for g in gate_results if not g.passed]
    
    # Priority 3: Sumarios de gates fallidos
    failed_summaries = "\n".join([f"- Gate Fallido: {g.name}" for g in failed_gates])
    add_required_or_fail(budget, failed_summaries, "Failed Gates Summaries")
    
    # Priority 4: Outputs de gates fallidos acotados
    failed_outputs = ""
    for g in failed_gates:
        out = f"\n[Output de {g.name}]\n{g.output}\n"
        if not budget.can_add(len(out) // 4):
            out = out[:max(0, budget.remaining * 4 - 100)] + "\n... [TRUNCADO OUTPUT]"
        if out:
            budget.add(len(out) // 4)
            failed_outputs += out
            
    # Extraer archivos relacionados buscando menciones directas en outputs
    related_files = []
    other_files = []
    for path in generated_files:
        if path in failed_outputs:
            related_files.append(path)
        else:
            other_files.append(path)
            
    # Priority 5: Archivos generados relacionados
    rel_files_str = ""
    for path in related_files:
        code = generated_files[path]
        f_str = f"\n### Archivo Relacionado: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n"
        if not budget.can_add(len(f_str) // 4):
            f_str = f_str[:max(0, budget.remaining * 4 - 100)] + f"\n{MD_FENCE}\n... [TRUNCADO ARCHIVO]"
        if f_str:
            budget.add(len(f_str) // 4)
            rel_files_str += f_str
            
    # Priority 6: Resto de archivos generados
    oth_files_str = ""
    for path in other_files:
        code = generated_files[path]
        f_str = f"\n### Archivo Adicional: `{path}`\n{MD_FENCE}python\n{code}\n{MD_FENCE}\n"
        if not budget.can_add(len(f_str) // 4):
            f_str = f_str[:max(0, budget.remaining * 4 - 100)] + f"\n{MD_FENCE}\n... [TRUNCADO ARCHIVO]"
        if f_str:
            budget.add(len(f_str) // 4)
            oth_files_str += f_str
            
    # Priority 7: Resumen de gates exitosos
    passed_gates = [g for g in gate_results if g.passed]
    passed_gates_str = "\n".join([f"- Gate Exitoso: {g.name}" for g in passed_gates])
    if budget.can_add(len(passed_gates_str) // 4):
        budget.add(len(passed_gates_str) // 4)
    else:
        passed_gates_str = ""
        
    prompt = f"""
    {gobernanza}
    
    Contexto: {issue_ctx}
    
    GATES FALLIDOS (CAUSA DEL BLOQUEO):
    {failed_summaries}
    {failed_outputs}
    
    CÓDIGO GENERADO RELACIONADO:
    {rel_files_str}
    
    RESTO DEL CÓDIGO GENERADO:
    {oth_files_str}
    
    GATES EXITOSOS (CONTEXTO):
    {passed_gates_str}
    """
    
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
def base_preflight() -> list[str]:
    """Valida que las herramientas base estén disponibles en el entorno antes de iniciar el SDLC."""
    errors = []
    tools = ["python", "git"]
    for tool in tools:
        try:
            if tool == "python":
                cmd = [sys.executable, "--version"]
            elif tool == "git":
                cmd = ["git", "--version"]
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            errors.append(f"La herramienta '{tool}' falló al ejecutarse. ¿Está instalada en el entorno activo?")
        except FileNotFoundError:
            errors.append(f"No se encontró el ejecutable para '{tool}'.")
    return errors

def tool_preflight(gate_plan) -> list[str]:
    """Valida herramientas de análisis dinámico de manera condicional basadas en QualityGatePlan."""
    errors = []
    tools = []
    if gate_plan.run_tests and gate_plan.test_framework == "pytest":
        tools.append("pytest")
    # unittest is part of the Python stdlib, no separate preflight needed
    if gate_plan.run_mypy: tools.append("mypy")
    if gate_plan.run_ruff: tools.append("ruff")
    if gate_plan.run_vulture: tools.append("vulture")
    
    for tool in tools:
        try:
            cmd = [sys.executable, "-m", tool, "--version"]
            subprocess.run(cmd, capture_output=True, check=True)
        except subprocess.CalledProcessError:
            errors.append(f"La herramienta '{tool}' falló al ejecutarse. ¿Está instalada en el entorno activo?")
        except FileNotFoundError:
            errors.append(f"No se encontró el ejecutable para '{tool}'.")
    return errors

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