import os
import sys
import pytest
from unittest.mock import MagicMock, patch
import ast
import json

# Allow importing orchestrator
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# R018 - Import safety
# This will fail if importing orchestrator makes network calls (e.g. Github, genai.Client)
import orchestrator

class StopPipeline(Exception):
    pass

@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=orchestrator.RuntimeClients)
    runtime.ai_client = MagicMock()
    runtime.github_client = MagicMock()
    runtime.repo = MagicMock()
    runtime.repo.get_issue.return_value = MagicMock(title="Test", body="Test body")
    return runtime

# =====================================================================
# R001 & R002: MyPy logic in run_pipeline
# =====================================================================
def test_R001_mypy_native_files(mock_runtime, tmp_path):
    # Setup context with native files
    repo_context = MagicMock()
    repo_context.structured_config.mypy_targets = ["src"]
    repo_context.structured_config.dependencies = []
    repo_context.structured_config.dev_dependencies = []
    repo_context.quality_policy = MagicMock()
    
    with patch("orchestrator.RepositoryContextManager") as MockRCM, \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_generate_acceptance_contract", return_value=MagicMock()), \
         patch("orchestrator.validate_contract_consistency", return_value=(True, [])), \
         patch("orchestrator._derive_gate_plan", return_value=MagicMock(run_mypy=True, run_tests=False, run_static_analysis=False)), \
         patch("orchestrator.validate_testing_policy_compatibility", return_value=[]), \
         patch("orchestrator.tool_preflight", return_value=[]), \
         patch("orchestrator.validate_contract_capabilities", return_value=(True, [])), \
         patch("orchestrator.validate_relevant_context_files", return_value=[]), \
         patch("orchestrator.agent_analyze_and_design", return_value={"actions": []}), \
         patch("orchestrator.validate_design", return_value=(True, [])), \
         patch("orchestrator.validate_generated_manifest", return_value=(True, "")), \
         patch("orchestrator.validate_final_state", return_value=(True, "")), \
         patch("orchestrator.agent_code_reviewer", return_value="Approved"), \
         patch("orchestrator.agent_update_architecture_doc", return_value="docs/ARCHITECTURE.md"), \
         patch("subprocess.run"), \
         patch("orchestrator.run_mypy", return_value=(True, "OK")) as mock_run_mypy, \
         patch("orchestrator.build_mypy_scope") as mock_build_scope:
         
         manager_instance = MockRCM.return_value
         manager_instance.build_repository_context.return_value = repo_context
         
         # Mock for report generation
         mock_runtime.ai_client.models.generate_content.return_value.text = "Mock Report"
         
         orig_reviewer = orchestrator.agent_code_reviewer
         orchestrator.agent_code_reviewer = MagicMock()
         orchestrator.agent_code_reviewer.return_value.approved = True
         orchestrator.agent_code_reviewer.return_value.design_conflict = False
         orchestrator.agent_code_reviewer.return_value.model_dump.return_value = {}
         
         orig_updater = orchestrator.agent_update_architecture_doc
         orchestrator.agent_update_architecture_doc = MagicMock()
         
         orig_reporter = orchestrator.agent_generate_execution_report
         orchestrator.agent_generate_execution_report = MagicMock()
         
         orig_manual = orchestrator.agent_update_user_manual
         orchestrator.agent_update_user_manual = MagicMock()
         
         orig_deploy = orchestrator.deploy_to_github
         orchestrator.deploy_to_github = MagicMock()
         
         orig_meta = orchestrator.write_transactional_metadata
         orchestrator.write_transactional_metadata = MagicMock()
         
         try:
             orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
         finally:
             orchestrator.agent_code_reviewer = orig_reviewer
             orchestrator.agent_update_architecture_doc = orig_updater
             orchestrator.agent_generate_execution_report = orig_reporter
             orchestrator.agent_update_user_manual = orig_manual
             orchestrator.deploy_to_github = orig_deploy
             orchestrator.write_transactional_metadata = orig_meta
             
         mock_run_mypy.assert_called_with([], repo_context.quality_policy)
         mock_build_scope.assert_not_called()

def test_R002_mypy_inferred_scope(mock_runtime, tmp_path):
    # Setup context without native files
    repo_context = MagicMock()
    repo_context.structured_config.mypy_targets = []
    repo_context.structured_config.dependencies = []
    repo_context.structured_config.dev_dependencies = []
    repo_context.quality_policy = MagicMock()
    
    with patch("orchestrator.RepositoryContextManager") as MockRCM, \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_generate_acceptance_contract", return_value=MagicMock()), \
         patch("orchestrator.validate_contract_consistency", return_value=(True, [])), \
         patch("orchestrator._derive_gate_plan", return_value=MagicMock(run_mypy=True, run_tests=False, run_static_analysis=False)), \
         patch("orchestrator.validate_testing_policy_compatibility", return_value=[]), \
         patch("orchestrator.tool_preflight", return_value=[]), \
         patch("orchestrator.validate_contract_capabilities", return_value=(True, [])), \
         patch("orchestrator.validate_relevant_context_files", return_value=[]), \
         patch("orchestrator.agent_analyze_and_design", return_value={"actions": []}), \
         patch("orchestrator.validate_design", return_value=(True, [])), \
         patch("orchestrator.validate_generated_manifest", return_value=(True, "")), \
         patch("orchestrator.validate_final_state", return_value=(True, "")), \
         patch("orchestrator.agent_code_reviewer", return_value="Approved"), \
         patch("orchestrator.agent_update_architecture_doc", return_value="docs/ARCHITECTURE.md"), \
         patch("subprocess.run"), \
         patch("orchestrator.run_mypy", return_value=(True, "OK")) as mock_run_mypy, \
         patch("orchestrator.build_mypy_scope", return_value=["a.py"]) as mock_build_scope:
         
         manager_instance = MockRCM.return_value
         manager_instance.build_repository_context.return_value = repo_context
         
         mock_runtime.ai_client.models.generate_content.return_value.text = "Mock Report"
         
         orig_reviewer = orchestrator.agent_code_reviewer
         orchestrator.agent_code_reviewer = MagicMock()
         orchestrator.agent_code_reviewer.return_value.approved = True
         orchestrator.agent_code_reviewer.return_value.design_conflict = False
         orchestrator.agent_code_reviewer.return_value.model_dump.return_value = {}
         
         orig_updater = orchestrator.agent_update_architecture_doc
         orchestrator.agent_update_architecture_doc = MagicMock()
         
         orig_reporter = orchestrator.agent_generate_execution_report
         orchestrator.agent_generate_execution_report = MagicMock()
         
         orig_manual = orchestrator.agent_update_user_manual
         orchestrator.agent_update_user_manual = MagicMock()
         
         orig_deploy = orchestrator.deploy_to_github
         orchestrator.deploy_to_github = MagicMock()
         
         orig_meta = orchestrator.write_transactional_metadata
         orchestrator.write_transactional_metadata = MagicMock()
         
         try:
             orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
         finally:
             orchestrator.agent_code_reviewer = orig_reviewer
             orchestrator.agent_update_architecture_doc = orig_updater
             orchestrator.agent_generate_execution_report = orig_reporter
             orchestrator.agent_update_user_manual = orig_manual
             orchestrator.deploy_to_github = orig_deploy
             orchestrator.write_transactional_metadata = orig_meta
             
         mock_build_scope.assert_called_once()
         mock_run_mypy.assert_called_with(["a.py"], repo_context.quality_policy)

# =====================================================================
# R003: MyPy normalization
# =====================================================================
def test_R003_mypy_normalization(tmp_path):
    config_content = "[mypy]\nfiles =  src , , src/**/*.py, src, src/**/*.py\n"
    manager = orchestrator.RepositoryContextManager(".", str(tmp_path / "logs"))
    config = manager._extract_project_configuration({"mypy.ini": config_content}, {})
    assert config.mypy_targets == ["src", "src/**/*.py"], "Debe eliminar vacíos, espacios, deduplicar preservando orden, y mantener globs"

# =====================================================================
# R004: Cache is_test
# =====================================================================
def test_R004a_cache_is_test_reclassification(tmp_path):
    import tempfile
    
    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_a(): pass", encoding="utf-8")
    
    manager = orchestrator.RepositoryContextManager(str(tmp_path), str(tmp_path / "logs"))
    
    # Run 1: pytest config says test_a.py is a test
    budget = orchestrator.ContextBudget(max_tokens=10000)
    
    with patch.object(manager, "_extract_project_configuration") as mock_ext:
        config1 = orchestrator.PythonProjectConfiguration()
        config1.pytest_patterns = ["test_*.py"]
        mock_ext.return_value = config1
        ctx1 = manager.build_repository_context("issue", budget)
        assert "test_a.py" in ctx1.test_index
        assert "test_a.py" not in ctx1.source_index
        
    # Run 2: same hash, but pytest config changed
    with patch.object(manager, "_extract_project_configuration") as mock_ext:
        config2 = orchestrator.PythonProjectConfiguration()
        config2.pytest_patterns = ["spec_*.py"] # now it shouldn't be a test
        mock_ext.return_value = config2
        ctx2 = manager.build_repository_context("issue", budget)
        assert "test_a.py" not in ctx2.test_index
        assert "test_a.py" in ctx2.source_index

def test_R004b_cache_is_test_reclassification_failure(tmp_path):
    import tempfile
    
    test_file = tmp_path / "test_a.py"
    test_file.write_text("def test_a(): pass", encoding="utf-8")
    manager = orchestrator.RepositoryContextManager(str(tmp_path), str(tmp_path / "logs"))
    budget = orchestrator.ContextBudget(max_tokens=10000)
    
    with patch.object(manager, "_extract_project_configuration") as mock_ext:
        config1 = orchestrator.PythonProjectConfiguration()
        config1.pytest_patterns = ["test_*.py"]
        mock_ext.return_value = config1
        manager.build_repository_context("issue", budget)
        
    with patch.object(manager, "_extract_project_configuration") as mock_ext:
        config2 = orchestrator.PythonProjectConfiguration()
        config2.pytest_patterns = ["spec_*.py"]
        mock_ext.return_value = config2 
        # Force failure during re-reading/analyzing
        with patch("orchestrator_core.repository_context.is_test_file", side_effect=Exception("Read error")) as mock_is_test:
            ctx2 = manager.build_repository_context("issue", budget)
            # Desired behavior: it should NOT silently reuse the old is_test classification
            assert "test_a.py" not in ctx2.test_index
            mock_is_test.assert_called()

# =====================================================================
# R005: Import graph exacto
# =====================================================================
def test_R005_import_graph_exacto():
    code = """
import package.module
import package.module as alias
from package.module import symbol
from package import module
from package import module as alias
from . import module
from .module import symbol
from .. import module
from ..package import symbol
"""
    tree = ast.parse(code)
    extracted = orchestrator.extract_imported_modules(tree, "src.sub.file")
    
    # Validation of structural extraction
    assert "package.module" in extracted
    assert "package.module.symbol" in extracted
    assert "package.module.alias" not in extracted # Alias is NOT a dependency
    
    # Now use resolve_imported_files
    all_py_files = [
        "package/module.py",
        "package/__init__.py",
        "src/sub/module.py",
        "src/module.py",
        "src/package/__init__.py",
        "package/mod.py",
        "package/module_extra.py",
        "src/sub/mod.py",
        "src/user.py"
    ]
    resolved = orchestrator.resolve_imported_files(extracted, ".", all_py_files)
    
    expected_resolved = {
        "package/module.py",
        "package/__init__.py",
        "src/sub/module.py",
        "src/module.py",
        "src/package/__init__.py"
    }
    assert set(resolved) == expected_resolved

# =====================================================================
# R006: No false import edge
# =====================================================================
def test_R006_no_false_import_edge():
    extracted = ["core.user_service"]
    resolved = orchestrator.resolve_imported_files(extracted, ".", ["core/user_service.py", "core/user.py"])
    assert "core/user_service.py" in resolved
    assert "core/user.py" not in resolved

# =====================================================================
# R007 & R008: Reviewer & Audit oversized
# =====================================================================
def test_R007_reviewer_oversized():
    # One file larger than max_tokens
    with pytest.raises(orchestrator.PreflightError):
        orchestrator.PromptContextBuilder.build_for_reviewer({"huge.py": "x" * 500000}, max_tokens=100)

def test_R008_audit_oversized():
    with pytest.raises(orchestrator.PreflightError):
        orchestrator.PromptContextBuilder.build_for_audit({"huge.py": "x" * 500000}, max_tokens=100)

# =====================================================================
# R009 & R010: Coder & Test Generator PromptBudget
# =====================================================================
def test_R009_coder_promptbudget(mock_runtime):
    action = {"filepath": "a.py", "operation": "MODIFY", "signatures": "", "instructions": "test"}
    file_contract = orchestrator.FileContract(
        filepath="a.py", required_exports=[], required_structures={}, 
        required_imports=[], forbidden_imports=[], required_decorators=[], 
        required_quality_tools=[], forbidden_quality_tools=[], 
        required_testing_techniques=[], forbidden_testing_techniques=[]
    )
    repo_context = MagicMock()
    repo_context.quality_policy = MagicMock()
    manager = MagicMock()
    manager.get_file_content.return_value = "small existing code"
    
    design = {"context": "x" * 600000} # Huge optional context
    feedback = "y" * 600000 # Huge optional feedback
    
    # Comportamiento FINAL esperado: NO PreflightError tardío, generate_content invocado, obligatorios presentes
    mock_runtime.ai_client.models.generate_content.return_value.text = "Mock Report"
    
    orchestrator.agent_implement_code(action, file_contract, design, {}, repo_context, mock_runtime, manager, feedback)
    
    mock_runtime.ai_client.models.generate_content.assert_called()
    call_args = mock_runtime.ai_client.models.generate_content.call_args[1]["contents"]
    assert "small existing code" in call_args
    assert "a.py" in call_args

def test_R009b_coder_promptbudget_huge_mandatory_preflight(mock_runtime):
    action = {"filepath": "a.py", "operation": "MODIFY", "signatures": "", "instructions": "test"}
    file_contract = MagicMock()
    file_contract.model_dump_json.return_value = '{"huge": "' + "z" * 500000 + '"}'
    repo_context = MagicMock()
    repo_context.quality_policy = MagicMock()
    manager = MagicMock()
    manager.get_file_content.return_value = "small code"
    
    design = {"context": "small context"}
    feedback = "small feedback"
    
    mock_runtime.ai_client.models.generate_content.return_value.text = "Mock Report"
    
    with pytest.raises(orchestrator.PreflightError):
        orchestrator.agent_implement_code(action, file_contract, design, {}, repo_context, mock_runtime, manager, feedback)
        
    assert mock_runtime.ai_client.models.generate_content.call_count == 0


def test_R010_test_generator_promptbudget(mock_runtime):
    action = {"filepath": "a.py", "operation": "CREATE", "signatures": "", "instructions": "test"}
    file_contract = orchestrator.FileContract(
        filepath="a.py", required_exports=[], required_structures={}, 
        required_imports=[], forbidden_imports=[], required_decorators=[], 
        required_quality_tools=[], forbidden_quality_tools=[], 
        required_testing_techniques=[], forbidden_testing_techniques=[]
    )
    repo_context = MagicMock()
    repo_context.quality_policy = MagicMock()
    repo_context.quality_policy.require_return_annotations = False
    repo_context.quality_policy.require_argument_annotations = False
    manager = MagicMock()
    manager.get_file_content.return_value = ""
    
    design = {"context": "z" * 600000} # Huge optional context
    feedback = "w" * 600000 # Huge optional feedback
    
    mock_runtime.ai_client.models.generate_content.return_value.text = "Mock Report"
    
    orchestrator.agent_generate_tests(action, file_contract, design, {}, repo_context, "pytest", mock_runtime, manager, feedback)
    
    mock_runtime.ai_client.models.generate_content.assert_called()
    call_args = mock_runtime.ai_client.models.generate_content.call_args[1]["contents"]
    assert "a.py" in call_args

# =====================================================================
# R011: Execution Report
# =====================================================================
def test_R011_execution_report(mock_runtime):
    # Huge pytest log
    pytest_log = "FAILED\n" * 50000
    sast_report = "x" * 100000
    design = {}
    generated = {"a.py": "code"}
    # Should not raise exception, should truncate intelligently
    mock_runtime.ai_client.models.generate_content.return_value = MagicMock(text="Mock")
    
    with patch("os.makedirs"), patch("builtins.open"):
        orchestrator.agent_generate_execution_report(design, generated, pytest_log, sast_report, 1, "Title", mock_runtime)
        
    mock_gen = mock_runtime.ai_client.models.generate_content
    mock_gen.assert_called()
    prompt_sent = mock_gen.call_args[1]["contents"]
    
    # The prompt should contain evidence of the manifest and represent FAILED messages
    assert "a.py" in prompt_sent
    assert "FAILED" in prompt_sent

# =====================================================================
# R012 & R013: Post-Mortem
# =====================================================================
def test_R012_postmortem_promptbudget(mock_runtime):
    gate = orchestrator.GateResult(attempt=1, name="Test", passed=False, output="x" * 500000, executed=True)
    generated = {"a.py": "code"}
    mock_runtime.ai_client.models.generate_content.return_value = MagicMock(text="Mock")
    
    with patch("os.makedirs"), patch("builtins.open"):
        result = orchestrator.agent_analyze_pipeline_failure(1, "Title", "Desc", {}, generated, [gate], mock_runtime)
        
    assert not result.startswith("Error de diagnostico"), "Ocurrió un PreflightError capturado internamente"
    mock_runtime.ai_client.models.generate_content.assert_called()
    call_args = mock_runtime.ai_client.models.generate_content.call_args[1]["contents"]
    assert "Title" in call_args

def test_R013_postmortem_related_files(mock_runtime):
    output = "error in src/a.py\n" + "x" * 500000 + "\nerror in src/b.py"
    gate = orchestrator.GateResult(attempt=1, name="Test", passed=False, output=output, executed=True)
    generated = {"src/a.py": "code a", "src/b.py": "code b", "src/c.py": "code c"}
    
    with patch.object(mock_runtime.ai_client.models, "generate_content") as mock_gen, \
         patch("os.makedirs"), patch("builtins.open"), patch("orchestrator.ensure_prompt_fits"):
        mock_gen.return_value = MagicMock(text="OK")
        
        result = orchestrator.agent_analyze_pipeline_failure(1, "Title", "Desc", {}, generated, [gate], mock_runtime)
        
        # Verify it didn't fail due to PreflightError
        assert not result.startswith("Error de diagnostico"), "Ocurrió un PreflightError capturado internamente"
        
        prompt = mock_gen.call_args[1]["contents"]
        
        # Check sections
        import re
        related_section = re.search(r'CÓDIGO GENERADO RELACIONADO:(.*?)RESTO DEL CÓDIGO GENERADO:', prompt, re.DOTALL)
        assert related_section, "Falta sección CÓDIGO GENERADO RELACIONADO"
        related_content = related_section.group(1)
        
        other_section = re.search(r'RESTO DEL CÓDIGO GENERADO:(.*?)GATES EXITOSOS', prompt, re.DOTALL)
        assert other_section, "Falta sección RESTO DEL CÓDIGO GENERADO"
        other_content = other_section.group(1)
        
        assert "src/a.py" in related_content
        assert "src/b.py" in related_content
        assert "src/c.py" in other_content
        
        assert "src/b.py" not in other_content

# =====================================================================
# R014 & R015: Architecture Updater
# =====================================================================
def test_R014_architecture_updater_success(mock_runtime):
    mock_runtime.ai_client.models.generate_content.return_value = MagicMock(text="```markdown\n# Doc\n```")
    repo_context = MagicMock()
    repo_context.repository_map = {"root": "."}
    
    with patch("os.makedirs"):
        with patch("builtins.open"):
            result = orchestrator.agent_update_architecture_doc(1, "Title", "Desc", {}, {}, "Old", [], "Diff", mock_runtime)
            assert result == "docs/ARCHITECTURE.md"

def test_R015_architecture_updater_mandatory_budget(mock_runtime):
    # Huge description, fixed instructions etc should overflow
    desc = "x" * 400000
    mock_runtime.ai_client.models.generate_content.return_value = MagicMock(text="Mock Report")
    
    with pytest.raises(orchestrator.PreflightError):
        orchestrator.agent_update_architecture_doc(1, "Title", desc, {}, {}, "Old", [], "Diff", mock_runtime)
    mock_runtime.ai_client.models.generate_content.assert_not_called()

# =====================================================================
# R016: API signatures
# =====================================================================
def test_R016_api_signatures():
    import inspect
    import ast
    
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
    }
    
    for name, expected_signature in expected_signatures.items():
        func = getattr(orchestrator, name)
        
        # Validamos que el objeto exportado tiene firma pública
        sig = inspect.signature(func)
        assert sig is not None
        
        # Extraemos el código fuente independientemente de su ubicación física
        source = inspect.getsource(func)
        tree = ast.parse(source)
        
        # Preservamos la validación exacta del AST
        sigs = orchestrator.extract_ast_signatures(tree)
        assert sigs[name] == expected_signature

# =====================================================================
# R017: Python-only
# =====================================================================
def test_R017_python_only():
    import inspect
    source = inspect.getsource(orchestrator.agent_implement_code)
    assert '".js"' not in source
    assert '".ts"' not in source
    assert '".html"' not in source
    assert '".css"' not in source

# =====================================================================
# R018: Import safety
# =====================================================================
def test_R018_import_safety():
    import ast
    with open(orchestrator.__file__, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())
        
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                func_name = ""
                if isinstance(node.value.func, ast.Name):
                    func_name = node.value.func.id
                elif isinstance(node.value.func, ast.Attribute):
                    func_name = node.value.func.attr
                assert func_name not in ["Client", "Github", "load_dotenv", "build_runtime_clients", "inject_into_ssl"], f"Llamada global prohibida: {func_name}"
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func_name = ""
            if isinstance(node.value.func, ast.Name):
                func_name = node.value.func.id
            elif isinstance(node.value.func, ast.Attribute):
                func_name = node.value.func.attr
            assert func_name not in ["Client", "Github", "load_dotenv", "build_runtime_clients", "inject_into_ssl"], f"Llamada global prohibida: {func_name}"





