import ast
import logging
import os
import re
import subprocess
import sys
from typing import Collection, Literal

from orchestrator_core.contract_validation import canonicalize_testing_technique
from orchestrator_core.project_config import is_test_file
from orchestrator_core.prompt_budget import PreflightError
from orchestrator_core.schemas import AcceptanceContract, PythonQualityPolicy, QualityGatePlan, RepositoryContext
from orchestrator_core.repository_context import RepositoryContextManager

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

