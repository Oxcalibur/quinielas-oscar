import os
import ast
import inspect
import sys
import importlib

import orchestrator
import orchestrator_core.prompt_budget
import orchestrator_core.import_graph
import orchestrator_core.runtime
import orchestrator_core.schemas
import orchestrator_core.ast_utils
import orchestrator_core.paths
import orchestrator_core.project_config
import orchestrator_core.context_budget
import orchestrator_core.repository_context
import orchestrator_core.prompt_context
import orchestrator_core.contract_validation
import orchestrator_core.quality_gates
import orchestrator_core.model_config
import orchestrator_core.response_parsing
import orchestrator_core.testing_policy
import orchestrator_core.exceptions
import orchestrator_core.planning_agents
import orchestrator_core.failure_analysis_agents
import orchestrator_core.logging_metadata
import textwrap

def test_MOD001_public_apis_still_available():
    """Comprueba que las APIs públicas relevantes continúan accesibles."""
    public_apis = [
        # Historical
        "run_mypy", "run_static_analysis", "agent_implement_code", "agent_generate_tests",
        "agent_generate_execution_report", "agent_update_architecture_doc", "agent_update_user_manual",
        "agent_analyze_pipeline_failure",
        
        # M14
        "write_local_log", "write_transactional_metadata", "agent_code_reviewer", "agent_security_audit", "run_pipeline",
        
        # M0
        "PromptBudget", "PromptPayload", "PreflightError", "ensure_prompt_fits",
        "add_required_or_fail", "fit_optional_text", "extract_imported_modules", "resolve_imported_files",
        
        # M1
        "RuntimeClients", "build_runtime_clients",
        
        # M2
        "FileAction", "ContextRequest", "ProjectDesign", "ReviewFinding",
        "CodeReviewResult", "QualityGatePlan", "PythonQualityPolicy",
        "PythonProjectConfiguration", "SecurityAuditResult", "ArchitectureConflict",
        "PythonFileSummary", "RepositoryIndexCache", "RequiredCall",
        "PreservedBehavior", "FileContract", "ContextBudget", "RepositoryContext",
        "AcceptanceContract", "GateResult", "ContractCapability",
        
        # M3
        "serialize_ast_signature", "extract_ast_signatures", "is_test_file",
        "parse_pyproject", "parse_requirements", "parse_pipfile",
        "parse_poetry_lock", "parse_setup_cfg", "parse_setup_py", "resolve_safe_path",
        
        # M4
        "estimate_repository_context_tokens",
        
        # M5
        "RepositoryContextManager",
        
        # M6
        "PromptContextBuilder",
        
        # M7
        "validate_relevant_context_files", "canonicalize_testing_technique",
        
        # M9-P1
        "MODEL_HEAVY", "ContractGenerationError",

        # M10-P1
        "MODEL_LIGHT", "MD_FENCE", "extract_code", "resolve_mocking_instruction",
        
        # M9
        "agent_generate_acceptance_contract", "agent_analyze_and_design",
    "write_local_log", "write_transactional_metadata",
        "agent_analyze_pipeline_failure",
        
        # M14
        "write_local_log", "write_transactional_metadata",
        
        "validate_contract_consistency", "_create_file_contract",
        "_check_forbidden_constructs", "_check_exports", "_check_tests",
        "_check_imports", "_check_patterns", "_check_calls", "_check_structures",
        "_get_decorator_name", "_check_decorators", "_check_preserved_signatures",
        "_check_testing_techniques", "validate_contractual_ast", "validate_design",
        "validate_generated_manifest", "validate_final_state",
        "_SUPPORTED_CODE_PATTERNS", "_SUPPORTED_STRUCTURE_CHECKS",
        
        # M8
        "reload_code_after_ruff", "validate_code_quality",
        "parse_compiler_output", "build_mypy_scope", "_derive_gate_plan",
        "validate_testing_policy_compatibility", "run_local_tests",
        "base_preflight", "tool_preflight"
    ]
    for api in public_apis:
        assert hasattr(orchestrator, api), f"API {api} no está disponible públicamente"

def test_MOD002_exact_public_signatures():
    """Comprueba las firmas exactas de la API exportada usando inspect.signature."""
    expected_signatures = {
        "run_mypy": "def run_mypy(filepaths: list[str], policy: 'PythonQualityPolicy') -> tuple[bool, str]",
        "run_static_analysis": "def run_static_analysis(generated_filepaths: list[str], plan: 'QualityGatePlan', test_paths: Collection[str] | None=None) -> tuple[bool, str]",
        "agent_implement_code": "def agent_implement_code(action: dict, file_contract: FileContract, design: dict, generated_so_far: dict[str, str], repo_context: RepositoryContext, runtime: RuntimeClients, context_manager: 'RepositoryContextManager', feedback: str='') -> str",
        "agent_generate_tests": "def agent_generate_tests(action: dict, file_contract: FileContract, generated_so_far: dict[str, str], issue_desc: str, repo_context: RepositoryContext, framework: Literal['pytest', 'unittest'], runtime: RuntimeClients, context_manager: 'RepositoryContextManager', feedback: str='') -> str",
        "agent_generate_execution_report": "def agent_generate_execution_report(design: dict, generated_files: dict[str, str], pytest_log: str, sast_report: str, issue_id: int, title: str, runtime: RuntimeClients) -> str",
        "agent_update_architecture_doc": "def agent_update_architecture_doc(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], current_arch_doc: str, gate_results: list[GateResult], git_diff: str, runtime: RuntimeClients) -> str",
        "agent_update_user_manual": "def agent_update_user_manual(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], runtime: RuntimeClients) -> str",
        "agent_analyze_pipeline_failure": "def agent_analyze_pipeline_failure(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], gate_results: list[GateResult], runtime: RuntimeClients) -> str",
        "agent_code_reviewer": "def agent_code_reviewer(design: dict, generated_files: dict[str, str], issue_desc: str, contract: AcceptanceContract, repo_context: RepositoryContext, runtime: RuntimeClients) -> CodeReviewResult",
        "agent_security_audit": "def agent_security_audit(design: dict, generated_files: dict[str, str], contract: AcceptanceContract, runtime: RuntimeClients, repo_context: RepositoryContext) -> SecurityAuditResult",
        "run_pipeline": "def run_pipeline(issue_id: int, run_id: str, run_log_dir: str, runtime: RuntimeClients) -> None",
        "build_runtime_clients": "def build_runtime_clients() -> RuntimeClients",
        "extract_code": "def extract_code(text, language=None)",
        "resolve_mocking_instruction": "def resolve_mocking_instruction(framework: Literal['pytest', 'unittest'], file_contract: FileContract, repo_context: RepositoryContext) -> str",
        "serialize_ast_signature": "def serialize_ast_signature(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str",
        "extract_ast_signatures": "def extract_ast_signatures(tree: ast.AST) -> dict[str, str]",
        "is_test_file": "def is_test_file(filepath: str, content: str=None, project_config: 'PythonProjectConfiguration'=None) -> bool",
        "parse_pyproject": "def parse_pyproject(content: str) -> dict",
        "parse_requirements": "def parse_requirements(content: str) -> list[str]",
        "parse_pipfile": "def parse_pipfile(content: str) -> dict",
        "parse_poetry_lock": "def parse_poetry_lock(content: str) -> list[str]",
        "parse_setup_cfg": "def parse_setup_cfg(content: str) -> list[str]",
        "parse_setup_py": "def parse_setup_py(content: str) -> dict",
        "resolve_safe_path": "def resolve_safe_path(root: str, relative_path: str) -> str",
        "estimate_repository_context_tokens": "def estimate_repository_context_tokens(repo_context: RepositoryContext, issue_description: str, contract: AcceptanceContract | None=None) -> int",
        "RepositoryContextManager.__init__": "def __init__(self, root_path='.', cache_dir=None)",
        "RepositoryContextManager.generate_repository_map": "def generate_repository_map(self) -> str",
        "RepositoryContextManager._extract_signatures": "def _extract_signatures(self, filepath: str) -> dict[str, str]",
        "RepositoryContextManager.get_file_content": "def get_file_content(self, relative_filepath) -> str",
        "RepositoryContextManager.read_architecture_document": "def read_architecture_document(self) -> str",
        "RepositoryContextManager._scan_config_files": "def _scan_config_files(self) -> tuple[dict[str, str], dict[str, str]]",
        "RepositoryContextManager._extract_project_configuration": "def _extract_project_configuration(self, project_configs: dict[str, str], dep_files: dict[str, str]) -> 'PythonProjectConfiguration'",
        "RepositoryContextManager._analyze_python_file": "def _analyze_python_file(self, filepath: str, project_config: 'PythonProjectConfiguration | None'=None) -> 'PythonFileSummary | None'",
        "RepositoryContextManager._detect_architecture_conflicts": "def _detect_architecture_conflicts(self, context: 'RepositoryContext')",
        "RepositoryContextManager._derive_quality_policy": "def _derive_quality_policy(self, context: 'RepositoryContext', issue_description: str)",
        "RepositoryContextManager._detect_testing_conventions": "def _detect_testing_conventions(self, context: 'RepositoryContext')",
        "RepositoryContextManager._load_cache": "def _load_cache(self) -> 'RepositoryIndexCache'",
        "RepositoryContextManager._save_cache": "def _save_cache(self, cache: 'RepositoryIndexCache')",
        "RepositoryContextManager._summarize_architecture_document": "def _summarize_architecture_document(self, full_content: str, budget_tokens: int) -> str",
        "RepositoryContextManager.build_repository_context": "def build_repository_context(self, issue_description: str, budget: 'ContextBudget') -> 'RepositoryContext'",
        "RepositoryContextManager._link_dependencies": "def _link_dependencies(self, context: 'RepositoryContext')",
        "RepositoryContextManager.select_relevant_files": "def select_relevant_files(self, context: 'RepositoryContext', issue_description: str, token_budget: int, max_files: int, dependency_depth: int) -> None",
        "PromptContextBuilder._estimate_tokens": "def _estimate_tokens(text: str) -> int",
        "PromptContextBuilder.build_for_coder": "def build_for_coder(action: dict, design: dict, generated_so_far: dict[str, str], repo_context: RepositoryContext, context_manager: 'RepositoryContextManager', budget: PromptBudget) -> PromptPayload",
        "PromptContextBuilder.build_for_tests": "def build_for_tests(action: dict, generated_so_far: dict[str, str], repo_context: RepositoryContext, context_manager: 'RepositoryContextManager', budget: PromptBudget) -> PromptPayload",
        "PromptContextBuilder.build_for_reviewer": "def build_for_reviewer(generated_files: dict[str, str], max_tokens: int=100000) -> list[PromptPayload]",
        "PromptContextBuilder.build_for_audit": "def build_for_audit(generated_files: dict[str, str], max_tokens: int=100000) -> list[PromptPayload]",
        "PromptContextBuilder.build_for_report": "def build_for_report(generated_files: dict[str, str], budget: PromptBudget) -> PromptPayload",
                "validate_relevant_context_files": "def validate_relevant_context_files(repo_context: 'RepositoryContext', contract: 'AcceptanceContract') -> list[str]",
        "canonicalize_testing_technique": "def canonicalize_testing_technique(technique: str) -> str",
        "validate_contract_consistency": "def validate_contract_consistency(contract: AcceptanceContract) -> tuple[bool, list[str]]",
        "_create_file_contract": "def _create_file_contract(filepath: str, contract: AcceptanceContract) -> 'FileContract'",
        "_check_forbidden_constructs": "def _check_forbidden_constructs(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]",
        "_check_exports": "def _check_exports(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]",
        "_check_tests": "def _check_tests(tree: ast.AST, filepath: str, contract: AcceptanceContract, repo_context=None) -> list[str]",
        "_check_imports": "def _check_imports(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]",
        "_check_patterns": "def _check_patterns(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]",
        "_check_calls": "def _check_calls(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]",
        "_check_structures": "def _check_structures(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]",
        "_get_decorator_name": "def _get_decorator_name(decorator_node: ast.expr) -> str",
        "_check_decorators": "def _check_decorators(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]",
        "_check_preserved_signatures": "def _check_preserved_signatures(tree: ast.AST, filepath: str, contract: AcceptanceContract) -> list[str]",
        "_check_testing_techniques": "def _check_testing_techniques(tree: ast.AST, filepath: str, contract: AcceptanceContract, repo_context=None) -> list[str]",
        "validate_contractual_ast": "def validate_contractual_ast(code: str, filepath: str, contract: AcceptanceContract, repo_context=None) -> list[str]",
        "validate_design": "def validate_design(design: dict, contract: AcceptanceContract) -> tuple[bool, list[str]]",
        "validate_generated_manifest": "def validate_generated_manifest(generated_files: dict[str, str], contract: AcceptanceContract, repo_context: RepositoryContext) -> tuple[bool, str]",
        "validate_final_state": "def validate_final_state(contract: AcceptanceContract) -> tuple[bool, str]",
        "PromptContextBuilder.build_for_docs": "def build_for_docs(design: dict, generated_files: dict[str, str], budget: PromptBudget) -> PromptPayload",
        "reload_code_after_ruff": "def reload_code_after_ruff(generated_files: dict[str, str], context_manager: 'RepositoryContextManager') -> None",
        "validate_code_quality": "def validate_code_quality(code: str, filepath: str, policy: 'PythonQualityPolicy') -> tuple[bool, str]",
        "parse_compiler_output": "def parse_compiler_output(log: str) -> dict[str, str]",
        "build_mypy_scope": "def build_mypy_scope(generated_files: dict[str, str], repo_context: 'RepositoryContext') -> list[str]",
        "_derive_gate_plan": "def _derive_gate_plan(repo_context: RepositoryContext, contract: AcceptanceContract) -> 'QualityGatePlan'",
        "validate_testing_policy_compatibility": "def validate_testing_policy_compatibility(framework: Literal['pytest', 'unittest', 'none'], contract: AcceptanceContract) -> list[str]",
        "run_local_tests": "def run_local_tests(test_filename: str, framework: str='pytest') -> tuple[bool, str]",
        "base_preflight": "def base_preflight() -> list[str]",
        "tool_preflight": "def tool_preflight(gate_plan) -> list[str]",
    }
    
    for name, expected_signature in expected_signatures.items():
        if '.' in name:
            cls_name, method_name = name.split('.')
            cls = getattr(orchestrator, cls_name)
            func = getattr(cls, method_name)
        else:
            func = getattr(orchestrator, name)
        sig = inspect.signature(func)
        assert sig is not None
        source = inspect.getsource(func)
        source = textwrap.dedent(source)
        tree = ast.parse(source)
        sigs = orchestrator.extract_ast_signatures(tree)
        actual_name = method_name if '.' in name else name
        assert sigs[actual_name] == expected_signature
        
        if '.' in name and cls_name == 'PromptContextBuilder':
            assert isinstance(inspect.getattr_static(cls, method_name), staticmethod)

def test_MOD003_llm_inventory():
    """Comprueba repository-wide que el inventario de llamadas LLM sigue siendo 11."""
    root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = []
    
    orchestrator_path = os.path.join(root_path, "orchestrator.py")
    if os.path.exists(orchestrator_path):
        target_files.append(orchestrator_path)
        
    core_path = os.path.join(root_path, "orchestrator_core")
    if os.path.exists(core_path):
        for f in os.listdir(core_path):
            if f.endswith(".py"):
                target_files.append(os.path.join(core_path, f))
                
    total_calls = 0
    for file_path in target_files:
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                tree = ast.parse(f.read())
            except SyntaxError:
                continue
                
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr == "generate_content":
                    total_calls += 1
                    
    assert total_calls == 11, f"LLM inventory must be exactly 11, found {total_calls}"

def test_MOD004_no_reverse_imports():
    """Comprueba repository-wide que ningún archivo bajo orchestrator_core importe orchestrator."""
    root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    core_path = os.path.join(root_path, "orchestrator_core")
    
    if not os.path.exists(core_path):
        return
        
    for root, _, files in os.walk(core_path):
        for f in files:
            if f.endswith(".py"):
                file_path = os.path.join(root, f)
                with open(file_path, "r", encoding="utf-8") as f_obj:
                    tree = ast.parse(f_obj.read())
                
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            assert alias.name != "orchestrator", f"Reverse import found in {file_path}"
                    elif isinstance(node, ast.ImportFrom):
                        if node.module == "orchestrator":
                            assert False, f"Reverse import found in {file_path}"

def test_MOD005_core_import_safe():
    """Comprueba que los módulos core existentes pueden importarse sin efectos laterales prohibidos."""
    assert orchestrator_core.prompt_budget is not None
    assert orchestrator_core.import_graph is not None
    assert orchestrator_core.runtime is not None
    assert orchestrator_core.schemas is not None
    assert orchestrator_core.ast_utils is not None
    assert orchestrator_core.paths is not None
    assert orchestrator_core.project_config is not None
    assert orchestrator_core.context_budget is not None
    assert orchestrator_core.repository_context is not None
    assert orchestrator_core.prompt_context is not None
    assert orchestrator_core.contract_validation is not None
    assert orchestrator_core.quality_gates is not None
    assert orchestrator_core.model_config is not None
    assert orchestrator_core.response_parsing is not None
    assert orchestrator_core.testing_policy is not None
    assert orchestrator_core.exceptions is not None
    assert orchestrator_core.planning_agents is not None
    assert orchestrator_core.failure_analysis_agents is not None
    assert orchestrator_core.logging_metadata is not None

def test_MOD006_identity_reexports():
    """Comprueba la identidad de los objetos públicos ya movidos."""
    # prompt_budget
    assert orchestrator.PromptBudget is orchestrator_core.prompt_budget.PromptBudget
    assert orchestrator.PromptPayload is orchestrator_core.prompt_budget.PromptPayload
    assert orchestrator.PreflightError is orchestrator_core.prompt_budget.PreflightError
    assert orchestrator.ensure_prompt_fits is orchestrator_core.prompt_budget.ensure_prompt_fits
    assert orchestrator.add_required_or_fail is orchestrator_core.prompt_budget.add_required_or_fail
    assert orchestrator.fit_optional_text is orchestrator_core.prompt_budget.fit_optional_text
    
    # import_graph
    assert orchestrator.extract_imported_modules is orchestrator_core.import_graph.extract_imported_modules
    assert orchestrator.resolve_imported_files is orchestrator_core.import_graph.resolve_imported_files
    
    # runtime
    assert orchestrator.RuntimeClients is orchestrator_core.runtime.RuntimeClients
    assert orchestrator.build_runtime_clients is orchestrator_core.runtime.build_runtime_clients
    
    # schemas
    schema_classes = [
        "FileAction", "ContextRequest", "ProjectDesign", "ReviewFinding",
        "CodeReviewResult", "QualityGatePlan", "PythonQualityPolicy",
        "PythonProjectConfiguration", "SecurityAuditResult", "ArchitectureConflict",
        "PythonFileSummary", "RepositoryIndexCache", "RequiredCall",
        "PreservedBehavior", "FileContract", "ContextBudget", "RepositoryContext",
        "AcceptanceContract", "GateResult", "ContractCapability"
    ]
    for cls in schema_classes:
        assert getattr(orchestrator, cls) is getattr(orchestrator_core.schemas, cls)
        
    # ast_utils
    assert orchestrator.serialize_ast_signature is orchestrator_core.ast_utils.serialize_ast_signature
    assert orchestrator.extract_ast_signatures is orchestrator_core.ast_utils.extract_ast_signatures
    
    # paths
    assert orchestrator.resolve_safe_path is orchestrator_core.paths.resolve_safe_path
    
    # project_config
    assert orchestrator.is_test_file is orchestrator_core.project_config.is_test_file
    assert orchestrator.parse_pyproject is orchestrator_core.project_config.parse_pyproject
    assert orchestrator.parse_requirements is orchestrator_core.project_config.parse_requirements
    assert orchestrator.parse_pipfile is orchestrator_core.project_config.parse_pipfile
    assert orchestrator.parse_poetry_lock is orchestrator_core.project_config.parse_poetry_lock
    assert orchestrator.parse_setup_cfg is orchestrator_core.project_config.parse_setup_cfg
    assert orchestrator.parse_setup_py is orchestrator_core.project_config.parse_setup_py
    
    # context_budget
    assert orchestrator.estimate_repository_context_tokens is orchestrator_core.context_budget.estimate_repository_context_tokens
    
    # repository_context
    assert orchestrator.RepositoryContextManager is orchestrator_core.repository_context.RepositoryContextManager
    
    # prompt_context
    assert orchestrator.PromptContextBuilder is orchestrator_core.prompt_context.PromptContextBuilder

    # contract_validation
    assert orchestrator.validate_relevant_context_files is orchestrator_core.contract_validation.validate_relevant_context_files
    assert orchestrator.canonicalize_testing_technique is orchestrator_core.contract_validation.canonicalize_testing_technique
    assert orchestrator.validate_contract_consistency is orchestrator_core.contract_validation.validate_contract_consistency
    assert orchestrator._create_file_contract is orchestrator_core.contract_validation._create_file_contract
    assert orchestrator._check_forbidden_constructs is orchestrator_core.contract_validation._check_forbidden_constructs
    assert orchestrator._check_exports is orchestrator_core.contract_validation._check_exports
    assert orchestrator._check_tests is orchestrator_core.contract_validation._check_tests
    assert orchestrator._check_imports is orchestrator_core.contract_validation._check_imports
    assert orchestrator._check_patterns is orchestrator_core.contract_validation._check_patterns
    assert orchestrator._check_calls is orchestrator_core.contract_validation._check_calls
    assert orchestrator._check_structures is orchestrator_core.contract_validation._check_structures
    assert orchestrator._get_decorator_name is orchestrator_core.contract_validation._get_decorator_name
    assert orchestrator._check_decorators is orchestrator_core.contract_validation._check_decorators
    assert orchestrator._check_preserved_signatures is orchestrator_core.contract_validation._check_preserved_signatures
    assert orchestrator._check_testing_techniques is orchestrator_core.contract_validation._check_testing_techniques
    assert orchestrator.validate_contractual_ast is orchestrator_core.contract_validation.validate_contractual_ast
    assert orchestrator.validate_design is orchestrator_core.contract_validation.validate_design
    assert orchestrator.validate_generated_manifest is orchestrator_core.contract_validation.validate_generated_manifest
    assert orchestrator.validate_final_state is orchestrator_core.contract_validation.validate_final_state
    assert orchestrator._SUPPORTED_CODE_PATTERNS is orchestrator_core.contract_validation._SUPPORTED_CODE_PATTERNS
    assert orchestrator._SUPPORTED_STRUCTURE_CHECKS is orchestrator_core.contract_validation._SUPPORTED_STRUCTURE_CHECKS

    # quality_gates
    assert orchestrator.run_static_analysis is orchestrator_core.quality_gates.run_static_analysis
    assert orchestrator.reload_code_after_ruff is orchestrator_core.quality_gates.reload_code_after_ruff
    assert orchestrator.validate_code_quality is orchestrator_core.quality_gates.validate_code_quality
    assert orchestrator.parse_compiler_output is orchestrator_core.quality_gates.parse_compiler_output
    assert orchestrator.build_mypy_scope is orchestrator_core.quality_gates.build_mypy_scope
    assert orchestrator.run_mypy is orchestrator_core.quality_gates.run_mypy
    assert orchestrator._derive_gate_plan is orchestrator_core.quality_gates._derive_gate_plan
    assert orchestrator.validate_testing_policy_compatibility is orchestrator_core.quality_gates.validate_testing_policy_compatibility
    assert orchestrator.run_local_tests is orchestrator_core.quality_gates.run_local_tests
    assert orchestrator.base_preflight is orchestrator_core.quality_gates.base_preflight
    assert orchestrator.tool_preflight is orchestrator_core.quality_gates.tool_preflight
    
    # model_config
    assert orchestrator.MODEL_HEAVY is orchestrator_core.model_config.MODEL_HEAVY
    assert orchestrator.MODEL_LIGHT is orchestrator_core.model_config.MODEL_LIGHT
    assert orchestrator.MD_FENCE is orchestrator_core.response_parsing.MD_FENCE
    assert orchestrator.extract_code is orchestrator_core.response_parsing.extract_code
    assert orchestrator.resolve_mocking_instruction is orchestrator_core.testing_policy.resolve_mocking_instruction
    
    # exceptions
    assert orchestrator.ContractGenerationError is orchestrator_core.exceptions.ContractGenerationError
    
    # planning_agents
    assert orchestrator.agent_generate_acceptance_contract is orchestrator_core.planning_agents.agent_generate_acceptance_contract
    assert orchestrator.agent_analyze_and_design is orchestrator_core.planning_agents.agent_analyze_and_design
    assert orchestrator.agent_code_reviewer is orchestrator_core.review_agents.agent_code_reviewer
    assert orchestrator.agent_security_audit is orchestrator_core.review_agents.agent_security_audit
    assert orchestrator.agent_update_architecture_doc is orchestrator_core.documentation_agents.agent_update_architecture_doc
    assert orchestrator.agent_update_user_manual is orchestrator_core.documentation_agents.agent_update_user_manual
    assert orchestrator.agent_generate_execution_report is orchestrator_core.documentation_agents.agent_generate_execution_report

    # failure_analysis_agents
    assert orchestrator.agent_analyze_pipeline_failure is orchestrator_core.failure_analysis_agents.agent_analyze_pipeline_failure

    # logging_metadata
    assert orchestrator.write_local_log is orchestrator_core.logging_metadata.write_local_log
    assert orchestrator.write_transactional_metadata is orchestrator_core.logging_metadata.write_transactional_metadata

def test_MOD007_no_duplicate_authoritative_implementations():
    """Comprueba que los símbolos ya movidos no mantengan una segunda implementación autoritativa en orchestrator.py."""
    root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    orchestrator_path = os.path.join(root_path, "orchestrator.py")
    
    with open(orchestrator_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    forbidden_classes = ["PromptBudget", "PromptPayload", "PreflightError", "RuntimeClients", "RepositoryContextManager",         "PromptContextBuilder",
        "validate_relevant_context_files", "canonicalize_testing_technique",
        "validate_contract_consistency", "_create_file_contract",
        "_check_forbidden_constructs", "_check_exports", "_check_tests",
        "_check_imports", "_check_patterns", "_check_calls", "_check_structures",
        "_get_decorator_name", "_check_decorators", "_check_preserved_signatures",
        "_check_testing_techniques", "validate_contractual_ast", "validate_design",
        "validate_generated_manifest", "validate_final_state",
        "_SUPPORTED_CODE_PATTERNS", "_SUPPORTED_STRUCTURE_CHECKS"] + [
        "FileAction", "ContextRequest", "ProjectDesign", "ReviewFinding",
        "CodeReviewResult", "QualityGatePlan", "PythonQualityPolicy",
        "PythonProjectConfiguration", "SecurityAuditResult", "ArchitectureConflict",
        "PythonFileSummary", "RepositoryIndexCache", "RequiredCall",
        "PreservedBehavior", "FileContract", "ContextBudget", "RepositoryContext",
        "AcceptanceContract", "GateResult", "ContractCapability", "ContractGenerationError"
    ]
    forbidden_functions = [
        "ensure_prompt_fits", "add_required_or_fail", "fit_optional_text",
        "extract_imported_modules", "resolve_imported_files", "build_runtime_clients",
        "serialize_ast_signature", "extract_ast_signatures", "is_test_file",
        "parse_pyproject", "parse_requirements", "parse_pipfile",
        "parse_poetry_lock", "parse_setup_cfg", "parse_setup_py", "resolve_safe_path",
        "estimate_repository_context_tokens",
        "validate_relevant_context_files", "canonicalize_testing_technique",
        "validate_contract_consistency", "_create_file_contract",
        "_check_forbidden_constructs", "_check_exports", "_check_tests",
        "_check_imports", "_check_patterns", "_check_calls", "_check_structures",
        "_get_decorator_name",        "_check_decorators", "_check_preserved_signatures",
        "_check_testing_techniques", "validate_contractual_ast", "validate_design",
        "validate_generated_manifest", "validate_final_state",
        "run_static_analysis", "reload_code_after_ruff", "validate_code_quality",
        "parse_compiler_output", "build_mypy_scope", "run_mypy",
        "_derive_gate_plan", "validate_testing_policy_compatibility", "run_local_tests",
        "base_preflight", "tool_preflight",
        "agent_generate_acceptance_contract", "agent_analyze_and_design",
    "write_local_log", "write_transactional_metadata"
    ]
    
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            assert node.name not in forbidden_classes, f"Duplicate implementation for class {node.name} found in orchestrator.py"
        elif isinstance(node, ast.FunctionDef):
            assert node.name not in forbidden_functions, f"Duplicate implementation for function {node.name} found in orchestrator.py"
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assert target.id not in ["_SUPPORTED_CODE_PATTERNS", "_SUPPORTED_STRUCTURE_CHECKS", "MODEL_HEAVY"], f"Duplicate implementation for {target.id} found in orchestrator.py"
