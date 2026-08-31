from pydantic import BaseModel, Field, ValidationError
from typing import Literal, Any
import os

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

class PythonQualityPolicy(BaseModel):
    require_argument_annotations: bool = Field(default=False, description="Si se requieren anotaciones de tipo para los argumentos de las funciones.")
    require_return_annotations: bool = Field(default=False, description="Si se requieren anotaciones de tipo para el retorno de las funciones.")
    mypy_strict: bool = Field(default=False, description="Si MyPy debe ejecutarse en modo estricto.")
    require_explicit_exports: bool = Field(default=False, description="Si los archivos de producción deben tener `__all__`.")

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

class RepositoryIndexCache(BaseModel):
    source_index: dict[str, PythonFileSummary] = Field(default_factory=dict)
    test_index: dict[str, PythonFileSummary] = Field(default_factory=dict)

class RequiredCall(BaseModel):
    name: str
    count: int = 1

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
    # New: authoritative repository documentation resolved from Issue references
    authoritative_context_files: dict[str, str] = Field(default_factory=dict, description="Documentos de referencia autoritativos resueltos antes de generar el contrato")
    resolved_authoritative_references: list[str] = Field(default_factory=list, description="Lista de identificadores autoritativos que fueron resueltos")

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