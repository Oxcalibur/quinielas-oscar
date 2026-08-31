import ast
import configparser
import hashlib
import json
import logging
import os
import re
import subprocess

from pydantic import ValidationError

from orchestrator_core.ast_utils import extract_ast_signatures
from orchestrator_core.paths import resolve_safe_path
from orchestrator_core.import_graph import extract_imported_modules, resolve_imported_files
from orchestrator_core.context_budget import estimate_repository_context_tokens
from orchestrator_core.project_config import (
    is_test_file,
    parse_pyproject,
    parse_requirements,
    parse_pipfile,
    parse_poetry_lock,
    parse_setup_cfg,
    parse_setup_py,
)
from orchestrator_core.schemas import (
    ArchitectureConflict,
    ContextBudget,
    PythonFileSummary,
    PythonProjectConfiguration,
    PythonQualityPolicy,
    RepositoryContext,
    RepositoryIndexCache,
)

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

    def _discover_authoritative_references(self, issue_description: str) -> list[tuple[str, str]]:
        refs = []
        import re

        path_matches = re.findall(r'[\w/\\.-]+\.(?:md|txt|rst)', issue_description, flags=re.IGNORECASE)
        for p in path_matches:
            refs.append(p)

        for line in issue_description.splitlines():
            idx = line.lower().find("source requirements")
            if idx != -1:
                val_str = line[idx + len("source requirements"):].strip('*: ')
                parts = val_str.split(',')
                for p in parts:
                    clean_ref = p.strip(' *')
                    if clean_ref:
                        refs.append(clean_ref)

        # Deduplicate
        unique_refs = list(dict.fromkeys(refs))

        # Normalize
        result = []
        for ref in unique_refs:
            search_str = ref
            sec_match = re.match(r'^(?:secci[oó]n|section)\s+(.+)$', ref, flags=re.IGNORECASE)
            if sec_match:
                search_str = sec_match.group(1).strip()
            result.append((ref, search_str))

        return result

    def _resolve_authoritative_documents(self, refs: list[tuple[str, str]], max_files: int = 5) -> tuple[dict[str, str], list[str]]:
        import os
        import re
        from orchestrator_core.paths import resolve_safe_path
        doc_contents = {}
        for root, dirs, files in os.walk(self.root_path):
            dirs[:] = [d for d in dirs if d not in self.ignored_dirs]
            for file in files:
                if file.lower().endswith(('.md', '.rst', '.txt')):
                    full_path = os.path.join(root, file)
                    rel = os.path.relpath(full_path, self.root_path).replace('\\', '/')
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            doc_contents[rel] = f.read()
                    except Exception:
                        pass

        candidates = refs

        doc_coverage = {df: [] for df in doc_contents}
        explicit_paths = set()
        resolved_candidates = set()

        for cand_orig, search_str in candidates:
            cand_resolved = False

            if cand_orig.lower().endswith(('.md', '.rst', '.txt')):
                try:
                    cand_path = resolve_safe_path(self.root_path, cand_orig)
                    rel = os.path.relpath(cand_path, self.root_path).replace('\\', '/')
                    if rel in doc_contents:
                        explicit_paths.add(rel)
                        doc_coverage[rel].append(search_str)
                        cand_resolved = True
                        resolved_candidates.add(search_str)
                        continue
                    else:
                        from orchestrator_core.prompt_budget import PreflightError
                        raise PreflightError(f"Requisito normativo explícito no encontrado: {cand_orig}")
                except PreflightError:
                    raise
                except Exception as e:
                    from orchestrator_core.prompt_budget import PreflightError
                    raise PreflightError(f"Requisito normativo explícito no encontrado: {cand_orig}")

            for df, content in doc_contents.items():
                if search_str.lower() in content.lower():
                    doc_coverage[df].append(search_str)
                    cand_resolved = True
                    resolved_candidates.add(search_str)

            if not cand_resolved:
                from orchestrator_core.prompt_budget import PreflightError
                raise PreflightError(f"Requisito normativo no encontrado: {cand_orig}")

        selected_docs = set()
        covered_so_far = set()
        all_resolved = set(c[1] for c in candidates)

        for p in explicit_paths:
            selected_docs.add(p)
            covered_so_far.update(doc_coverage[p])

        remaining_docs = set(df for df in doc_contents if doc_coverage[df] and df not in selected_docs)

        while covered_so_far != all_resolved and remaining_docs:
            best_doc = min(remaining_docs, key=lambda df: (-len(set(doc_coverage[df]) - covered_so_far), df))
            new_cov = set(doc_coverage[best_doc]) - covered_so_far
            if not new_cov:
                break

            selected_docs.add(best_doc)
            covered_so_far.update(doc_coverage[best_doc])
            remaining_docs.remove(best_doc)

        final = {df: doc_contents[df] for df in selected_docs}
        return final, list(resolved_candidates)

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
                        try:
                            with open(full_path, "r", encoding="utf-8") as text_f:
                                text_content = text_f.read()
                            current_is_test = is_test_file(relative_path, text_content, context.structured_config)

                            summary = cached_summary.model_copy(deep=True)
                            summary.is_test = current_is_test
                            files_from_cache += 1
                        except Exception as e:
                            logging.warning(
                                f"No se pudo reclasificar desde cache '{relative_path}': {e}. "
                                "Se reanalizara el archivo completo."
                            )
                            summary = self._analyze_python_file(full_path, context.structured_config)
                            if summary:
                                files_analyzed += 1
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

        auth_refs = self._discover_authoritative_references(issue_description)
        if auth_refs:
            try:
                auth_docs, resolved_refs = self._resolve_authoritative_documents(auth_refs, max_files=budget.maximum_full_files)
            except Exception as e:
                from orchestrator_core.prompt_budget import PreflightError
                if isinstance(e, PreflightError):
                    raise
                raise PreflightError(f"Technical error resolving authoritative documents: {e}")
            context.authoritative_context_files = auth_docs
            context.resolved_authoritative_references = resolved_refs
        else:
            context.authoritative_context_files = {}
            context.resolved_authoritative_references = []

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
