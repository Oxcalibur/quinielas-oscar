import ast
import fnmatch
import hashlib
import os

from orchestrator_core.ast_utils import (
    extract_ast_signatures,
)

from orchestrator_core.paths import (
    resolve_safe_path,
)

from orchestrator_core.project_config import (
    is_test_file,
)

from orchestrator_core.schemas import (
    AcceptanceContract,
    FileContract,
    RepositoryContext,
)

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

