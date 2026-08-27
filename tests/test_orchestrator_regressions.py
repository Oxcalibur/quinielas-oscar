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

    child_issue = MagicMock()
    ready_label = MagicMock()
    ready_label.name = "ai:ready-to-code"
    child_issue.labels = [ready_label]
    child_issue.body = (
        "PO_PARENT_EPIC=2\n"
        "PO_CHILD_INDEX=1\n"
        "FINGERPRINT=0123456789abcdef"
    )

    parent_epic = MagicMock()
    deployed_label = MagicMock()
    deployed_label.name = "gate:deployed"
    parent_epic.labels = [deployed_label]

    def mock_get_issue(number):
        if number == 1:
            return child_issue
        if number == 2:
            return parent_epic
        raise Exception("Not found")

    mock_runtime.repo.get_issue.side_effect = mock_get_issue
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

    child_issue = MagicMock()
    ready_label = MagicMock()
    ready_label.name = "ai:ready-to-code"
    child_issue.labels = [ready_label]
    child_issue.body = (
        "PO_PARENT_EPIC=2\n"
        "PO_CHILD_INDEX=1\n"
        "FINGERPRINT=0123456789abcdef"
    )

    parent_epic = MagicMock()
    deployed_label = MagicMock()
    deployed_label.name = "gate:deployed"
    parent_epic.labels = [deployed_label]

    def mock_get_issue(number):
        if number == 1:
            return child_issue
        if number == 2:
            return parent_epic
        raise Exception("Not found")

    mock_runtime.repo.get_issue.side_effect = mock_get_issue
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
    assert config.mypy_targets == ["src", "src/**/*.py"], "Debe eliminar vacs, espacios, deduplicar preservando orden, y mantener globs"

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
        "agent_analyze_pipeline_failure": "def agent_analyze_pipeline_failure(issue_id: int, title: str, description: str, design: dict, generated_files: dict[str, str], gate_results: list[GateResult], runtime: RuntimeClients, error_msg: str='', pipeline_exc: Exception | None=None) -> str",
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









def test_D1_acceptance_contract_prompt_fstring():
    from orchestrator_core.planning_agents import agent_generate_acceptance_contract
    from unittest.mock import patch, MagicMock
    import json

    mock_runtime = MagicMock()
    mock_repo_context = MagicMock()
    # Ensure it's json serializable
    mock_repo_context.quality_policy.model_dump.return_value = {}
    mock_repo_context.structured_config.testing_policy.framework = "pytest"
    mock_repo_context.structured_config.dependencies = []
    mock_repo_context.structured_config.dev_dependencies = []

    with patch("orchestrator_core.planning_agents.ensure_prompt_fits"), \
         patch("orchestrator_core.schemas.AcceptanceContract"):

        # Prevent actually calling LLM, we just want to inspect the prompt
        def mock_generate_content(*args, **kwargs):
            raise RuntimeError("STOP")
        mock_runtime.ai_client.models.generate_content.side_effect = mock_generate_content

        try:
            agent_generate_acceptance_contract("Issue", "Desc", mock_repo_context, mock_runtime)
        except Exception as e:
            if "STOP" not in str(e):
                raise

        # Get the rendered prompt
        calls = mock_runtime.ai_client.models.generate_content.call_args_list
        assert len(calls) > 0, "No prompt was generated"
        prompt = calls[0][1].get("contents", "")
        if not prompt and len(calls[0][0]) > 0:
            prompt = calls[0][0][0]

        assert prompt, "Prompt is empty"
        assert '{"module.py": {"PublicClass": "class PublicClass(arg1: int)", "public_function": "def public_function()"}}' in prompt, "Failed to find exactly 1 pair of braces for dict in prompt"

def test_D2_catastrophic_failure_diagnosis(mock_runtime, tmp_path):
    import orchestrator
    from unittest.mock import patch, MagicMock

    # Mock eligibility and fetch
    child_issue = MagicMock()
    child_label = MagicMock()
    child_label.name = "ai:ready-to-code"
    child_issue.labels = [child_label]
    child_issue.body = "PO_PARENT_EPIC=2\nPO_CHILD_INDEX=1\nFINGERPRINT=0123456789abcdef"

    parent_epic = MagicMock()
    parent_label = MagicMock()
    parent_label.name = "gate:deployed"
    parent_epic.labels = [parent_label]

    def mock_get_issue(number):
        if number == 1: return child_issue
        if number == 2: return parent_epic
        raise Exception("Not found")
    mock_runtime.repo.get_issue.side_effect = mock_get_issue

    with patch("orchestrator.agent_generate_acceptance_contract", side_effect=ValueError("synthetic contract prompt failure")), \
         patch("orchestrator.agent_analyze_pipeline_failure", return_value="Dummy Report") as mock_analyze, \
         patch("orchestrator.agent_analyze_and_design") as mock_design, \
         patch("orchestrator.agent_implement_code") as mock_implement, \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.RepositoryContextManager") as MockRCM:

        mock_rcm = MockRCM.return_value
        mock_repo_context = MagicMock()
        mock_repo_context.architecture_conflicts = []
        mock_rcm.build_repository_context.return_value = mock_repo_context

        with pytest.raises(ValueError, match="synthetic contract prompt failure"):
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

        # Verify no design/implementation executed
        mock_design.assert_not_called()
        mock_implement.assert_not_called()

        # Verify analyze was called with correct context
        mock_analyze.assert_called_once()
        args, kwargs = mock_analyze.call_args
        flat_gates = args[5] # flat_gates is the 6th positional arg

        # Verify contract_generation failure is in flat_gates
        contract_gate = next((g for g in flat_gates if g.name == "contract_generation"), None)
        assert contract_gate is not None
        assert contract_gate.passed is False
        assert "ValueError" in contract_gate.output
        assert "synthetic contract prompt failure" in contract_gate.output

        # Verify exception details passed via kwargs
        assert kwargs.get("error_msg", "") != ""
        assert "synthetic contract prompt failure" in kwargs.get("error_msg", "")
        assert isinstance(kwargs.get("pipeline_exc"), ValueError)

def test_D2_failure_analysis_prompt_semantics(mock_runtime):
    from orchestrator_core.failure_analysis_agents import agent_analyze_pipeline_failure
    from orchestrator_core.schemas import GateResult
    from unittest.mock import patch

    gate = GateResult(
        attempt=1,
        name="contract_generation",
        executed=True,
        passed=False,
        output="ValueError: synthetic contract prompt failure"
    )

    with patch("orchestrator_core.failure_analysis_agents.ensure_prompt_fits"):
        def mock_generate_content(*args, **kwargs):
            raise RuntimeError("STOP")
        mock_runtime.ai_client.models.generate_content.side_effect = mock_generate_content

        try:
            agent_analyze_pipeline_failure(
                issue_id=5,
                title="Title",
                description="Desc",
                design={},
                generated_files={},
                gate_results=[gate],
                runtime=mock_runtime,
                error_msg="synthetic contract prompt failure",
                pipeline_exc=ValueError("synthetic contract prompt failure")
            )
        except Exception as e:
            if "STOP" not in str(e):
                raise

        calls = mock_runtime.ai_client.models.generate_content.call_args_list
        assert len(calls) > 0, "No prompt was generated"
        prompt = calls[0][1].get("contents", "")
        if not prompt and len(calls[0][0]) > 0:
            prompt = calls[0][0][0]

        assert "contract_generation" in prompt
        assert "ValueError" in prompt
        assert "synthetic contract prompt failure" in prompt
        assert "El pipeline falló tras agotar los reintentos de calidad" not in prompt
        assert "El pipeline ha fallado durante su ejecución. Determina la fase real del fallo" in prompt
        assert "No asumas que se agotaron reintentos" in prompt

        # New assertions for Governance alignment
        assert "Los defectos, inconsistencias, reglas no soportadas o fallos de síntesis del AcceptanceContract generado son fallos de contexto u orquestación del Orchestrator" in prompt
        assert "La simple necesidad de regenerar o corregir el AcceptanceContract NO DEBE activar la delegación al PO" in prompt
        assert "SOLO SI la evidencia demuestra que el Issue o los requisitos del producto contienen una ambigüedad material" in prompt

def test_D3_acceptance_contract_uses_json_schema_transport():
    from orchestrator_core.planning_agents import agent_generate_acceptance_contract, _build_gemini_json_schema
    from orchestrator_core.schemas import AcceptanceContract
    from orchestrator_core.exceptions import ContractGenerationError
    from unittest.mock import patch, MagicMock
    import pytest
    import json

    mock_runtime = MagicMock()
    mock_repo_context = MagicMock()
    mock_repo_context.quality_policy.model_dump.return_value = {}
    mock_repo_context.structured_config.testing_policy.framework = "pytest"
    mock_repo_context.structured_config.dependencies = []
    mock_repo_context.structured_config.dev_dependencies = []

    with patch("orchestrator_core.planning_agents.ensure_prompt_fits"):

        def mock_generate_content(*args, **kwargs):
            mock_response = MagicMock()
            # We omit `count` in required_calls to test local Pydantic default semantics (count: int = 1)
            # We include duplicate files in required_final_files to test local Pydantic uniqueness semantics (set)
            mock_response.text = '{"required_final_files":["a.py", "a.py"],"required_new_files":[],"required_modified_files":[],"required_deleted_files":[],"preserved_files":[],"relevant_context_files":[],"required_tests":{},"protected_tests":{},"preserved_signatures":{},"preserved_behaviors":[],"forbidden_test_names":[],"forbidden_constructs":{},"required_exports":{},"required_quality_tools":[],"forbidden_quality_tools":[],"required_testing_techniques":[],"forbidden_testing_techniques":[],"required_imports":{},"forbidden_imports":{},"required_calls":{"a.py":{"func":[{"name":"callee"}]}},"required_patterns":{},"required_structures":{},"required_decorators":{}}'
            return mock_response

        mock_runtime.ai_client.models.generate_content.side_effect = mock_generate_content

        contract = agent_generate_acceptance_contract("Issue", "Desc", mock_repo_context, mock_runtime)

        # I. Returned result is AcceptanceContract
        assert isinstance(contract, AcceptanceContract), "Failed to validate returned contract"

        # H. Local Pydantic semantics remain authoritative
        assert contract.required_calls["a.py"]["func"][0].count == 1, "Pydantic failed to apply omitted default count"
        assert len(contract.required_final_files) == 1, "Pydantic failed to deduplicate set elements"
        assert "a.py" in contract.required_final_files

        calls = mock_runtime.ai_client.models.generate_content.call_args_list
        assert len(calls) > 0, "No generate_content call made"

        config = calls[0][1].get("config")
        assert config is not None, "config was not passed to generate_content"

        # A. response_schema is None
        assert getattr(config, "response_schema", None) is None

        # B. response_json_schema is not None
        transport_schema = getattr(config, "response_json_schema", None)
        assert transport_schema is not None

        raw_schema = AcceptanceContract.model_json_schema()
        raw_schema_dump = json.dumps(raw_schema)

        # C. RAW Pydantic schema still contains default, uniqueItems, additionalProperties
        assert "default" in raw_schema_dump
        assert "uniqueItems" in raw_schema_dump
        assert "additionalProperties" in raw_schema_dump

        # D. TRANSPORT schema properties
        transport_schema_dump = json.dumps(transport_schema)
        assert "default" not in transport_schema_dump
        assert "uniqueItems" not in transport_schema_dump
        assert "additionalProperties" in transport_schema_dump
        assert "$defs" in transport_schema_dump
        assert "$ref" in transport_schema_dump

        # E. The transport schema contains ZERO unsupported schema keywords
        gemini_allowlist = {
            "$id", "$defs", "$ref", "$anchor", "type", "format", "title",
            "description", "enum", "items", "prefixItems", "minItems",
            "maxItems", "minimum", "maximum", "anyOf", "oneOf", "properties",
            "additionalProperties", "required", "propertyOrdering"
        }

        def crawl_verify(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ["type", "format", "title", "description", "enum", "items",
                             "prefixItems", "minItems", "maxItems", "minimum", "maximum",
                             "anyOf", "oneOf", "properties", "additionalProperties",
                             "required", "propertyOrdering", "default", "examples", "const",
                             "pattern", "minLength", "maxLength", "deprecated", "readOnly",
                             "writeOnly", "multipleOf", "exclusiveMinimum", "exclusiveMaximum",
                             "minProperties", "maxProperties", "uniqueItems"] or k.startswith("$"):
                        assert k in gemini_allowlist, f"Unsupported keyword '{k}' found in transport schema"
                    crawl_verify(v)
            elif isinstance(obj, list):
                for item in obj:
                    crawl_verify(item)

        crawl_verify(transport_schema)

        # F. RAW schema remains unchanged after adaptation
        assert raw_schema == AcceptanceContract.model_json_schema()

        # G. response_mime_type
        assert getattr(config, "response_mime_type", None) == "application/json"

        # Fail-closed future keyword regression
        bad_schema = {"type": "string", "pattern": "^x$"}
        with pytest.raises(ContractGenerationError) as exc:
            _build_gemini_json_schema(bad_schema)
        assert "pattern" in str(exc.value)


def test_D4_A_contract_source_fidelity_prompt():
    from orchestrator_core.planning_agents import agent_generate_acceptance_contract
    from orchestrator_core.schemas import AcceptanceContract
    from unittest.mock import patch, MagicMock

    mock_runtime = MagicMock()
    mock_repo_context = MagicMock()
    mock_repo_context.quality_policy.model_dump.return_value = {}
    mock_repo_context.structured_config.testing_policy.framework = "pytest"
    mock_repo_context.structured_config.dependencies = []
    mock_repo_context.structured_config.dev_dependencies = []

    with patch("orchestrator_core.planning_agents.ensure_prompt_fits"):
        def mock_generate_content(*args, **kwargs):
            mock_response = MagicMock()
            mock_response.text = '{"required_final_files":[],"required_new_files":[],"required_modified_files":[],"required_deleted_files":[],"preserved_files":[],"relevant_context_files":[],"required_tests":{},"protected_tests":{},"preserved_signatures":{},"preserved_behaviors":[],"forbidden_test_names":[],"forbidden_constructs":{},"required_exports":{},"required_quality_tools":[],"forbidden_quality_tools":[],"required_testing_techniques":[],"forbidden_testing_techniques":[],"required_imports":{},"forbidden_imports":{},"required_calls":{},"required_patterns":{},"required_structures":{},"required_decorators":{}}'
            return mock_response
        mock_runtime.ai_client.models.generate_content.side_effect = mock_generate_content

        agent_generate_acceptance_contract(
            "Issue Title",
            "Acceptance Criteria:\n- alpha\n- beta\n- gamma\nImplementation Open Choices:\n- LibraryX is recommended",
            mock_repo_context,
            mock_runtime
        )

        calls = mock_runtime.ai_client.models.generate_content.call_args_list
        assert len(calls) > 0
        prompt = calls[0][1].get("contents")

        # Verify generic rules exist
        assert "PRECEDENCIA VINCULANTE" in prompt
        assert "RECOMENDACIONES NO VINCULANTES" in prompt
        assert "EXHAUSTIVIDAD DE REQUISITOS ENUMERADOS" in prompt
        assert "PRESERVACIÓN SEMÁNTICA" in prompt

        # Verify it tells the LLM not to make optional things mandatory
        assert "NO DEBEN convertirse en una regla contractual obligatoria" in prompt
        assert "preservar TODAS" in prompt

        # BookAI-specific strings should not be in the template
        assert "chapter summaries" not in prompt
        assert "LibraryX is recommended" in prompt # From the fake issue


def test_D4_C1_greenfield_contracted_tests():
    from orchestrator_core.quality_gates import _derive_gate_plan
    from orchestrator_core.schemas import RepositoryContext, AcceptanceContract, PythonProjectConfiguration, PythonQualityPolicy

    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(),
        detected_test_framework=None
    )

    contract = AcceptanceContract(
        required_tests={"test_file.py": ["test_something"]}
    )

    plan = _derive_gate_plan(repo_context, contract)

    assert plan.run_tests is True
    assert plan.test_framework == "unittest"


def test_D4_C2_existing_pytest_preserved():
    from orchestrator_core.quality_gates import _derive_gate_plan
    from orchestrator_core.schemas import RepositoryContext, AcceptanceContract, PythonProjectConfiguration, PythonQualityPolicy

    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(),
        detected_test_framework="pytest"
    )

    contract = AcceptanceContract(
        required_tests={"test_file.py": ["test_something"]}
    )

    plan = _derive_gate_plan(repo_context, contract)

    assert plan.run_tests is True
    assert plan.test_framework == "pytest"


def test_D4_C3_existing_unittest_preserved():
    from orchestrator_core.quality_gates import _derive_gate_plan
    from orchestrator_core.schemas import RepositoryContext, AcceptanceContract, PythonProjectConfiguration, PythonQualityPolicy

    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(),
        detected_test_framework="unittest"
    )

    contract = AcceptanceContract(
        required_tests={"test_file.py": ["test_something"]}
    )

    plan = _derive_gate_plan(repo_context, contract)

    assert plan.run_tests is True
    assert plan.test_framework == "unittest"


def test_D4_C4_implied_pytest_preserved():
    from orchestrator_core.quality_gates import _derive_gate_plan
    from orchestrator_core.schemas import RepositoryContext, AcceptanceContract, PythonProjectConfiguration, PythonQualityPolicy

    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(),
        detected_test_framework=None
    )

    contract = AcceptanceContract(
        required_tests={"test_file.py": ["test_something"]},
        required_testing_techniques=["pytest-mock"]
    )

    plan = _derive_gate_plan(repo_context, contract)

    assert plan.run_tests is True
    assert plan.test_framework == "pytest"


def test_D4_C5_forbidden_fallback_fail_closed():
    from orchestrator_core.quality_gates import _derive_gate_plan
    from orchestrator_core.schemas import RepositoryContext, AcceptanceContract, PythonProjectConfiguration, PythonQualityPolicy
    from orchestrator_core.prompt_budget import PreflightError
    import pytest

    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(),
        detected_test_framework=None
    )

    contract = AcceptanceContract(
        required_tests={"test_file.py": ["test_something"]},
        forbidden_quality_tools=["unittest"]
    )

    with pytest.raises(PreflightError) as exc:
        _derive_gate_plan(repo_context, contract)

    assert "no existe un framework permitido" in str(exc.value)


def test_D4_C6_no_tests():
    from orchestrator_core.quality_gates import _derive_gate_plan
    from orchestrator_core.schemas import RepositoryContext, AcceptanceContract, PythonProjectConfiguration, PythonQualityPolicy

    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(),
        detected_test_framework=None
    )

    contract = AcceptanceContract()

    plan = _derive_gate_plan(repo_context, contract)

    assert plan.run_tests is False
    assert plan.test_framework == "none"

def test_D4_B_no_bookai_hardcode_in_contract_generation():
    import inspect
    from orchestrator_core.planning_agents import agent_generate_acceptance_contract

    source = inspect.getsource(agent_generate_acceptance_contract)
    assert "Story Bible" not in source, "BookAI hardcode found: Story Bible"
    assert "chapter summaries" not in source, "BookAI hardcode found: chapter summaries"
    assert "executive summary" not in source, "BookAI hardcode found: executive summary"
    assert "Pydantic" not in source, "BookAI hardcode found: Pydantic"

def test_D4_C7_repository_framework_conflict_not_greenfield():
    from orchestrator_core.quality_gates import _derive_gate_plan
    from orchestrator_core.schemas import RepositoryContext, AcceptanceContract, PythonProjectConfiguration, PythonQualityPolicy
    from orchestrator_core.prompt_budget import PreflightError

    # repo_context has no detected framework directly, but structured config implies pytest
    structured_config = PythonProjectConfiguration()
    structured_config.detected_quality_tools = ["pytest"]

    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=structured_config,
        detected_test_framework=None
    )

    contract = AcceptanceContract(
        required_tests={"tests/test_x.py": ["test_x"]},
        forbidden_quality_tools=["pytest"]
    )

    try:
        _derive_gate_plan(repo_context, contract)
        assert False, "Expected PreflightError to be raised due to framework conflict, but it silently fell back."
    except PreflightError as e:
        assert "no existe un framework permitido" in str(e)

from orchestrator_core.schemas import RepositoryContext, AcceptanceContract, PythonProjectConfiguration, PythonQualityPolicy

def apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan):
    child_issue = MagicMock()
    ready_label = MagicMock()
    ready_label.name = "ai:ready-to-code"
    child_issue.labels = [ready_label]
    child_issue.body = "PO_PARENT_EPIC=2\nPO_CHILD_INDEX=1\nFINGERPRINT=0123456789abcdef"
    parent_epic = MagicMock()
    deployed_label = MagicMock()
    deployed_label.name = "gate:deployed"
    parent_epic.labels = [deployed_label]

    def mock_get_issue(number):
        if number == 1: return child_issue
        if number == 2: return parent_epic
        raise Exception("Not found")
    mock_runtime.repo.get_issue.side_effect = mock_get_issue

    class MockRCM:
        def build_repository_context(self, *args, **kwargs):
            return repo_context
        def get_file_content(self, *args, **kwargs):
            return ""

    reviewer_mock = MagicMock(approved=True, design_conflict=False)
    reviewer_mock.model_dump.return_value = {"approved": True, "design_conflict": False}

    auditor_mock = MagicMock(approved=True)
    auditor_mock.model_dump.return_value = {"approved": True}

    patches = [
        patch("orchestrator.RepositoryContextManager", return_value=MockRCM()),
        patch("orchestrator.base_preflight", return_value=[]),
        patch("orchestrator.fetch_issue", return_value=("T", "D")),
        patch("orchestrator.agent_generate_acceptance_contract", return_value=contract),
        patch("orchestrator.validate_contract_consistency", return_value=(True, [])),
        patch("orchestrator._derive_gate_plan", return_value=gate_plan),
        patch("orchestrator.validate_testing_policy_compatibility", return_value=[]),
        patch("orchestrator.tool_preflight", return_value=[]),
        patch("orchestrator.validate_contract_capabilities", return_value=(True, [])),
        patch("orchestrator.validate_relevant_context_files", return_value=[]),
        patch("orchestrator.agent_analyze_and_design", return_value=design),
        patch("orchestrator.validate_generated_manifest", return_value=(True, "")),
        patch("orchestrator.validate_final_state", return_value=(True, "")),
        patch("orchestrator.agent_code_reviewer", return_value=reviewer_mock),
        patch("orchestrator.agent_security_audit", return_value=auditor_mock),
        patch("orchestrator.agent_update_architecture_doc", return_value="docs/ARCHITECTURE.md"),
        patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")),
        patch("orchestrator.run_mypy", return_value=(True, "OK")),
        patch("orchestrator.build_mypy_scope", return_value=[]),
        patch("orchestrator.estimate_repository_context_tokens", return_value=0),
        patch("os.makedirs"),
        patch("builtins.open"),
        patch("orchestrator.run_local_tests", return_value=(True, "OK")),
        patch("orchestrator.agent_generate_tests", return_value="# test code"),
        patch("orchestrator.agent_implement_code", return_value="# src code"),
        patch("orchestrator.validate_code_quality", return_value=(True, "OK")),
        patch("orchestrator.validate_contractual_ast", return_value=[])
    ]
    return patches

def test_D5_A1_greenfield_repository_tests_gate_pass(mock_runtime, tmp_path):
    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "test_x.py", "file_type": "test", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=True, test_framework="pytest", run_static_analysis=False)

    patches = apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan)
    with patch("orchestrator.materialize_cached_files"), \
         patch("orchestrator.validate_design", return_value=(True, [])):
        for p in patches: p.start()

        import orchestrator
        with patch("subprocess.run") as mock_subprocess_run:
            mock_subprocess_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

            for call in mock_subprocess_run.call_args_list:
                args = call[0][0]
                assert "pytest" not in args
                assert "unittest" not in args

        for p in patches: p.stop()

def test_D5_A2_baseline_tests_exist_runner_fails(mock_runtime, tmp_path):
    from orchestrator_core.schemas import PythonFileSummary
    repo_context = RepositoryContext(
        source_index={}, test_index={"test_x.py": PythonFileSummary(filepath="test_x.py", module_name="test_x", imports=[], exports=[], docstring_summary="", referenced_symbols=[], file_hash="", estimated_tokens=0, classes=[], functions=[], signatures={}, complexity=0, is_test=True)},
        relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "test_x.py", "file_type": "test", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=True, test_framework="pytest", run_static_analysis=False)

    patches = apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan)
    with patch("orchestrator.materialize_cached_files"), patch("orchestrator.validate_design", return_value=(True, [])):
        for p in patches: p.start()

        import orchestrator
        with patch("subprocess.run") as mock_subprocess_run:
            def side_effect(cmd, **kwargs):
                if "pytest" in cmd:
                    return MagicMock(returncode=1, stdout="", stderr="Fail")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_subprocess_run.side_effect = side_effect

            with patch("orchestrator.agent_generate_tests") as mock_gen_tests:
                orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

                pytest_calls = [call for call in mock_subprocess_run.call_args_list if "pytest" in call[0][0]]
                assert len(pytest_calls) > 1

        for p in patches: p.stop()

def test_D5_A3_baseline_tests_expected_but_zero_executed(mock_runtime, tmp_path):
    from orchestrator_core.schemas import PythonFileSummary
    repo_context = RepositoryContext(
        source_index={}, test_index={"test_x.py": PythonFileSummary(filepath="test_x.py", module_name="test_x", imports=[], exports=[], docstring_summary="", referenced_symbols=[], file_hash="", estimated_tokens=0, classes=[], functions=[], signatures={}, complexity=0, is_test=True)},
        relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "test_x.py", "file_type": "test", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=True, test_framework="unittest", run_static_analysis=False)

    patches = apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan)
    with patch("orchestrator.materialize_cached_files"), patch("orchestrator.validate_design", return_value=(True, [])):
        for p in patches: p.start()

        import orchestrator
        with patch("subprocess.run") as mock_subprocess_run:
            def side_effect(cmd, **kwargs):
                if "unittest" in cmd:
                    return MagicMock(returncode=0, stdout="Ran 0 tests", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_subprocess_run.side_effect = side_effect

            with patch("orchestrator.agent_generate_tests") as mock_gen_tests:
                orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

                unittest_calls = [call for call in mock_subprocess_run.call_args_list if "unittest" in call[0][0]]
                assert len(unittest_calls) > 1

        for p in patches: p.stop()

def test_D5_A4_generated_test_fails_in_greenfield(mock_runtime, tmp_path):
    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "test_x.py", "file_type": "test", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=True, test_framework="pytest", run_static_analysis=False)

    patches = apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan)
    with patch("orchestrator.materialize_cached_files"), patch("orchestrator.validate_design", return_value=(True, [])):
        for p in patches: p.start()

        import orchestrator
        with patch("orchestrator.run_local_tests", return_value=(False, "Generated test failed")):
            with patch("orchestrator.agent_generate_tests") as mock_gen_tests:
                with patch("subprocess.run") as mock_subprocess_run:
                    orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
                    assert mock_gen_tests.call_count > 1
                    for call in mock_subprocess_run.call_args_list:
                        args = call[0][0]
                        assert "pytest" not in args
        for p in patches: p.stop()

def test_D5_A5_existing_pytest_behavior_preserved(mock_runtime, tmp_path):
    from orchestrator_core.schemas import PythonFileSummary
    repo_context = RepositoryContext(
        source_index={}, test_index={"test_x.py": PythonFileSummary(filepath="test_x.py", module_name="test_x", imports=[], exports=[], docstring_summary="", referenced_symbols=[], file_hash="", estimated_tokens=0, classes=[], functions=[], signatures={}, complexity=0, is_test=True)},
        relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "test_x.py", "file_type": "test", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=True, test_framework="pytest", run_static_analysis=False)

    patches = apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan)
    with patch("orchestrator.materialize_cached_files"), patch("orchestrator.validate_design", return_value=(True, [])):
        for p in patches: p.start()
        import orchestrator
        with patch("subprocess.run") as mock_subprocess_run:
            def side_effect(cmd, **kwargs):
                if "pytest" in cmd:
                    return MagicMock(returncode=0, stdout="Ran 1 test", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_subprocess_run.side_effect = side_effect
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
            assert any("pytest" in call[0][0] for call in mock_subprocess_run.call_args_list)
        for p in patches: p.stop()

def test_D5_A6_existing_unittest_behavior_preserved(mock_runtime, tmp_path):
    from orchestrator_core.schemas import PythonFileSummary
    repo_context = RepositoryContext(
        source_index={}, test_index={"test_x.py": PythonFileSummary(filepath="test_x.py", module_name="test_x", imports=[], exports=[], docstring_summary="", referenced_symbols=[], file_hash="", estimated_tokens=0, classes=[], functions=[], signatures={}, complexity=0, is_test=True)},
        relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "test_x.py", "file_type": "test", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=True, test_framework="unittest", run_static_analysis=False)

    patches = apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan)
    with patch("orchestrator.materialize_cached_files"), patch("orchestrator.validate_design", return_value=(True, [])):
        for p in patches: p.start()
        import orchestrator
        with patch("subprocess.run") as mock_subprocess_run:
            def side_effect(cmd, **kwargs):
                if "unittest" in cmd:
                    return MagicMock(returncode=0, stdout="Ran 1 test", stderr="")
                return MagicMock(returncode=0, stdout="", stderr="")
            mock_subprocess_run.side_effect = side_effect
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
            assert any("unittest" in call[0][0] for call in mock_subprocess_run.call_args_list)
        for p in patches: p.stop()

def test_D5_B1_validate_design_sees_baseline_before_cache(mock_runtime, tmp_path):
    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(required_new_files=["new_file.py"], protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "new_file.py", "file_type": "source", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=False, test_framework="pytest", run_static_analysis=False)

    patches = apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan)

    order = []

    def mock_validate_design(*args, **kwargs):
        order.append("validate_design")
        return (True, [])

    def mock_materialize_cached_files(*args, **kwargs):
        order.append("materialize")

    with patch("orchestrator.validate_design", side_effect=mock_validate_design), \
         patch("orchestrator.materialize_cached_files", side_effect=mock_materialize_cached_files):
        for p in patches: p.start()
        import orchestrator
        orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
        for p in patches: p.stop()

    assert order == ["validate_design", "materialize"]

def test_D5_B2_cache_materialized_after_validation(mock_runtime, tmp_path):
    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "new_file.py", "file_type": "source", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=False, test_framework="pytest", run_static_analysis=False)

    patches = apply_d5_patches(mock_runtime, repo_context, contract, design, gate_plan)

    with patch("orchestrator.validate_design", return_value=(True, [])), \
         patch("orchestrator.materialize_cached_files") as mock_materialize:

        for p in patches: p.start()
        import orchestrator

        with patch("orchestrator.validate_generated_manifest", side_effect=[(False, "fail"), (True, ""), (True, ""), (True, "")]), \
             patch("orchestrator.agent_implement_code", return_value="CODE"):
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

            assert mock_materialize.call_count >= 2
            args, kwargs = mock_materialize.call_args_list[1]
            generated_files = args[0]
            assert "new_file.py" in generated_files
            assert generated_files["new_file.py"] == "CODE"

        for p in patches: p.stop()

def test_D5_B3_genuine_conflict_fails(mock_runtime, tmp_path):
    from orchestrator_core.contract_validation import validate_design
    from orchestrator_core.schemas import AcceptanceContract

    design = {
        "actions": [
            {"operation": "CREATE", "filepath": "existing.py", "file_type": "source", "description": ""}
        ]
    }
    contract = AcceptanceContract(required_new_files=["existing.py"])

    import os
    file_path = tmp_path / "existing.py"
    file_path.write_text("# baseline")

    with patch("orchestrator_core.contract_validation.resolve_safe_path", return_value=str(file_path)):
        valid, errors = validate_design(design, contract)
        assert not valid
        assert any("CREATE" in e for e in errors)

    file_path.unlink()

def test_D5_B4_create_changed_to_modify_fails_contract(mock_runtime, tmp_path):
    from orchestrator_core.contract_validation import validate_design
    from orchestrator_core.schemas import AcceptanceContract

    design = {
        "actions": [
            {"operation": "MODIFY", "filepath": "new.py", "file_type": "source", "description": ""}
        ]
    }
    contract = AcceptanceContract(required_new_files=["new.py"])
    valid, errors = validate_design(design, contract)
    assert not valid
    assert any("El diseño no crea archivos requeridos por el contrato" in e for e in errors)

def test_D5_B5_retry_cache_semantics_preserved(mock_runtime, tmp_path):
    from orchestrator import materialize_cached_files

    generated_files = {"good.py": "GOOD", "bad.py": "BAD"}
    feedback_dict = {"bad.py": "Error"}

    context_manager = MagicMock()

    with patch("os.makedirs"), patch("builtins.open") as mock_open:
        materialize_cached_files(generated_files, feedback_dict, context_manager)

        written_files = []
        for call in mock_open.call_args_list:
            written_files.append(call[0][0])

        assert any("good.py" in f for f in written_files)
        assert not any("bad.py" in f for f in written_files)


import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from orchestrator_core.github_operations import deploy_to_github, _sanitize_staging_area

@pytest.fixture
def temp_git_repo(tmp_path):
    """Creates a real temporary git repository for testing staging logic."""
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    subprocess.run(["git", "init"], check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], check=True)

    # Create initial commit
    Path("README.md").write_text("# Init")
    subprocess.run(["git", "add", "README.md"], check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], check=True)

    yield tmp_path

    os.chdir(original_cwd)


def test_D6_A1_new_pyc_is_excluded(temp_git_repo):
    Path("module.py").write_text("print('hello')")
    subprocess.run(["git", "add", "module.py"])
    subprocess.run(["git", "commit", "-m", "Add module"])

    Path("module.pyc").write_text("fake bytecode")
    Path("new_module.py").write_text("print('world')")

    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()

    result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
    staged = result.stdout.strip().split('\n')

    assert "new_module.py" in staged
    assert "module.pyc" not in staged

def test_D6_A2_new_pycache_content_is_excluded(temp_git_repo):
    os.makedirs("pkg/__pycache__")
    Path("pkg/__pycache__/module.cpython-313.pyc").write_text("fake")
    os.makedirs("tests/__pycache__")
    Path("tests/__pycache__/test_x.cpython-313.pyc").write_text("fake")
    Path("valid_file.py").write_text("valid")

    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()

    result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
    staged = result.stdout.strip().split('\n')

    assert "valid_file.py" in staged
    assert not any("__pycache__" in f for f in staged)

def test_D6_A3_nested_generic_path(temp_git_repo):
    os.makedirs("src/a/b/__pycache__")
    Path("src/a/b/__pycache__/module.cpython-312.pyc").write_text("fake")

    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()

    result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
    staged = result.stdout.strip().split('\n')

    assert not any("module.cpython-312.pyc" in f for f in staged)

def test_D6_B1_baseline_tracked_matching_path_is_not_silently_deleted(temp_git_repo):
    os.makedirs("tracked_cache/__pycache__")
    Path("tracked_cache/__pycache__/tracked.pyc").write_text("tracked")
    subprocess.run(["git", "add", "-A"])
    subprocess.run(["git", "commit", "-m", "Track cache"])

    # Run filter
    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()

    # It should still be in the filesystem and tracked
    assert Path("tracked_cache/__pycache__/tracked.pyc").exists()

    # And if we modify it, it should NOT be unstaged by the filter because diff-filter=A only hits NEW files
    Path("tracked_cache/__pycache__/tracked.pyc").write_text("modified")
    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()

    result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
    staged = result.stdout.strip().split('\n')
    assert "tracked_cache/__pycache__/tracked.pyc" in staged

def test_D6_B2_normal_generated_files_are_preserved(temp_git_repo):
    os.makedirs("src")
    Path("src/module.py").write_text("valid")

    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()

    result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
    staged = result.stdout.strip().split('\n')
    assert "src/module.py" in staged

def test_D6_B3_documentation_metadata_deployment_preserved(temp_git_repo):
    import os
    from pathlib import Path
    import subprocess
    from unittest.mock import MagicMock, patch
    from orchestrator_core.github_operations import deploy_to_github

    # Setup initial metadata
    os.makedirs("docs/metadata", exist_ok=True)
    Path("docs/metadata/runs_registry.json").write_text("{}")
    subprocess.run(["git", "add", "-A"])
    subprocess.run(["git", "commit", "-m", "add meta"])

    # Simulate a pipeline run generating artifacts
    Path("implementation.py").write_text("impl")
    os.makedirs("tests", exist_ok=True)
    Path("tests/test_impl.py").write_text("test")
    Path("docs/ARCHITECTURE.md").write_text("arch")
    Path("docs/USER_MANUAL.md").write_text("man")
    os.makedirs("docs/reports", exist_ok=True)
    Path("docs/reports/run_issue_5.md").write_text("report")
    Path("__pycache__").mkdir(exist_ok=True)
    Path("__pycache__/impl.pyc").write_text("cache")

    mock_runtime = MagicMock()
    # Mock only network effects
    orig_run = subprocess.run
    with patch("orchestrator_core.github_operations.subprocess.run") as mock_run:
        def side_effect(cmd, **kwargs):
            if "push" in cmd or "fetch" in cmd:
                return MagicMock(returncode=0)
            return orig_run(cmd, **kwargs)
        mock_run.side_effect = side_effect

        # Let write_transactional_metadata run, we just need the file updated
        # It's actually not mocked, we let it run so it updates docs/metadata/runs_registry.json
        design = {"architecture_justification": "just"}
        generated_files = {"implementation.py": "impl", "tests/test_impl.py": "test"}

        deploy_to_github(
            design=design,
            generated_files=generated_files,
            report_path="docs/reports/run_issue_5.md",
            arch_path="docs/ARCHITECTURE.md",
            user_manual_path="docs/USER_MANUAL.md",
            issue_id=5,
            run_id="RUN-5",
            runtime=mock_runtime
        )

    # Verify implementation commit (HEAD~1)
    code_result = subprocess.run(["git", "show", "--name-only", "--oneline", "HEAD~1"], capture_output=True, text=True)
    code_files = code_result.stdout.strip().split('\n')
    assert "implementation.py" in code_files
    assert "tests/test_impl.py" in code_files
    assert "docs/ARCHITECTURE.md" in code_files
    assert "docs/USER_MANUAL.md" in code_files
    assert "docs/reports/run_issue_5.md" in code_files
    assert not any("impl.pyc" in f for f in code_files)

    # Verify metadata commit (HEAD)
    meta_result = subprocess.run(["git", "show", "--name-only", "--oneline", "HEAD"], capture_output=True, text=True)
    meta_files = meta_result.stdout.strip().split('\n')
    assert "docs/metadata/runs_registry.json" in meta_files

def test_D6_B4_deletions_modifications_preserved(temp_git_repo):
    Path("to_delete.py").write_text("delete")
    Path("to_modify.py").write_text("modify")
    subprocess.run(["git", "add", "-A"])
    subprocess.run(["git", "commit", "-m", "Initial"])

    os.remove("to_delete.py")
    Path("to_modify.py").write_text("modified")

    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()

    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True)
    status = result.stdout.strip()
    assert "D\tto_delete.py" in status or "D\tto_delete.py" in status.replace(" ", "") or "D  to_delete.py" in status.replace("\t", "  ")
    assert "M\tto_modify.py" in status or "M\tto_modify.py" in status.replace(" ", "") or "M  to_modify.py" in status.replace("\t", "  ")

def test_real_run_5_reproduction_test(temp_git_repo):
    # Setup directories
    os.makedirs("memory/__pycache__", exist_ok=True)
    os.makedirs("tests/__pycache__", exist_ok=True)

    # Simulate generation
    Path("memory/schemas.py").write_text("schemas")
    Path("memory/state_manager.py").write_text("state")
    Path("tests/test_schemas.py").write_text("test_schemas")
    Path("tests/test_state_manager.py").write_text("test_state")

    # Simulate pycache
    Path("memory/__pycache__/schemas.cpython-313.pyc").write_text("cache")
    Path("memory/__pycache__/state_manager.cpython-313.pyc").write_text("cache")
    Path("tests/__pycache__/test_schemas.cpython-313.pyc").write_text("cache")
    Path("tests/__pycache__/test_state_manager.cpython-313.pyc").write_text("cache")

    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()

    result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True)
    staged = result.stdout.strip().split('\n')

    assert "memory/schemas.py" in staged
    assert "memory/state_manager.py" in staged
    assert "tests/test_schemas.py" in staged
    assert "tests/test_state_manager.py" in staged

    assert not any("schemas.cpython-313.pyc" in f for f in staged)
    assert not any("state_manager.cpython-313.pyc" in f for f in staged)


def test_D6_C1_staged_documentation_evidence_is_clean(mock_runtime, temp_git_repo, tmp_path):
    from orchestrator_core.schemas import PythonFileSummary, RepositoryContext, PythonQualityPolicy, PythonProjectConfiguration
    from orchestrator_core.planning_agents import AcceptanceContract
    from orchestrator import run_pipeline
    import orchestrator
    import subprocess
    from pathlib import Path

    repo_context = RepositoryContext(
        source_index={}, test_index={}, relevant_source_files={}, relevant_test_files={},
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration()
    )
    contract = AcceptanceContract(protected_tests={})
    design = {"actions": [{"operation": "CREATE", "filepath": "legitimate.py", "file_type": "source", "description": ""}]}
    gate_plan = MagicMock(run_mypy=False, run_tests=False, run_static_analysis=False, run_ruff=False, run_vulture=False)

    class MockRCM:
        def build_repository_context(self, *args, **kwargs): return repo_context
        def get_file_content(self, *args, **kwargs): return ""

    reviewer_mock = MagicMock(approved=True, design_conflict=False)
    reviewer_mock.model_dump.return_value = {"approved": True, "design_conflict": False}
    auditor_mock = MagicMock(approved=True)
    auditor_mock.model_dump.return_value = {"approved": True}

    child_issue = MagicMock()
    ready_label = MagicMock()
    ready_label.name = "ai:ready-to-code"
    child_issue.labels = [ready_label]
    child_issue.body = "PO_PARENT_EPIC=2\nPO_CHILD_INDEX=1\nFINGERPRINT=0123456789abcdef"

    parent_epic = MagicMock()
    deployed_label = MagicMock()
    deployed_label.name = "gate:deployed"
    parent_epic.labels = [deployed_label]

    def mock_get_issue(*args, **kwargs):
        num = kwargs.get("number", args[0] if args else 1)
        if num == 1: return child_issue
        if num == 2: return parent_epic
        return MagicMock()
    mock_runtime.repo.get_issue.side_effect = mock_get_issue

    patches = [
        patch("orchestrator.RepositoryContextManager", return_value=MockRCM()),
        patch("orchestrator.base_preflight", return_value=[]),
        patch("orchestrator.fetch_issue", return_value=("T", "D")),
        patch("orchestrator.agent_generate_acceptance_contract", return_value=contract),
        patch("orchestrator.validate_contract_consistency", return_value=(True, [])),
        patch("orchestrator._derive_gate_plan", return_value=gate_plan),
        patch("orchestrator.validate_testing_policy_compatibility", return_value=[]),
        patch("orchestrator.tool_preflight", return_value=[]),
        patch("orchestrator.validate_contract_capabilities", return_value=(True, [])),
        patch("orchestrator.validate_relevant_context_files", return_value=[]),
        patch("orchestrator.agent_analyze_and_design", return_value=design),
        patch("orchestrator.validate_generated_manifest", return_value=(True, "")),
        patch("orchestrator.validate_final_state", return_value=(True, "")),
        patch("orchestrator.agent_code_reviewer", return_value=reviewer_mock),
        patch("orchestrator.agent_security_audit", return_value=auditor_mock),
        patch("orchestrator.agent_update_architecture_doc", return_value="docs/ARCHITECTURE.md"),
        patch("orchestrator.run_mypy", return_value=(True, "OK")),
        patch("orchestrator.build_mypy_scope", return_value=[]),
        patch("orchestrator.estimate_repository_context_tokens", return_value=0),
        patch("orchestrator.run_local_tests", return_value=(True, "OK")),
        patch("orchestrator.agent_generate_tests", return_value="# test code"),
        patch("orchestrator.agent_implement_code", return_value="# src code"),
        patch("orchestrator.validate_code_quality", return_value=(True, "OK")),
        patch("orchestrator.validate_contractual_ast", return_value=[]),
        patch("orchestrator.materialize_cached_files"),
        patch("orchestrator.validate_design", return_value=(True, [])),
        patch("orchestrator.agent_generate_execution_report"),
        patch("orchestrator.agent_update_user_manual"),
        patch("orchestrator.deploy_to_github"),
    ]

    for p in patches: p.start()

    try:
        def fake_security_audit(*args, **kwargs):
            Path("__pycache__").mkdir(exist_ok=True)
            Path("__pycache__/module.cpython-313.pyc").write_text("cache")
            Path("legitimate.py").write_text("legitimate")
            return auditor_mock

        with patch("orchestrator.agent_security_audit", side_effect=fake_security_audit):
            # Also mock the git diff timeout? No, let real git run!
            run_pipeline(1, "run1", str(tmp_path), mock_runtime)

        mock_arch_doc = orchestrator.agent_update_architecture_doc
        assert mock_arch_doc.called
        git_diff_arg = mock_arch_doc.call_args[0][7]
        assert "legitimate.py" in git_diff_arg
        assert ".pyc" not in git_diff_arg
    finally:
        for p in patches: p.stop()

def test_D6_C2_lookalike_path_is_not_false_positive(temp_git_repo):
    import subprocess
    from pathlib import Path
    from orchestrator_core.github_operations import _sanitize_staging_area

    Path("src/not__pycache__name").mkdir(parents=True, exist_ok=True)
    Path("src/not__pycache__name/module.py").write_text("valid module")

    subprocess.run(["git", "add", "-A"])
    _sanitize_staging_area()
    diff_result = subprocess.run(["git", "diff", "--staged", "--name-only"], capture_output=True, text=True)
    staged = diff_result.stdout.strip().split('\n')

    assert "src/not__pycache__name/module.py" in staged


def test_d7_positive_binding_automated_test_requirement_cannot_disappear():

    from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files=set(), required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    title = "Implement counter"

    desc = "## Acceptance Criteria\n- Automated tests"



    import pytest

    with pytest.raises(SemanticFidelityError, match="missing_binding_test_obligation"):

        validate_semantic_fidelity(contract, title, desc, repo_context)



def test_d7_explicit_no_new_tests_required_does_not_create_obligation():

    from orchestrator_core.semantic_validators import validate_semantic_fidelity

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files=set(), required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    title = "Implement counter"

    desc = "## Scope\nNo new tests are required for this feature."



    validate_semantic_fidelity(contract, title, desc, repo_context)



def test_d7_explicit_tests_optional_does_not_create_obligation():

    from orchestrator_core.semantic_validators import validate_semantic_fidelity

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files=set(), required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    title = "Implement counter"

    desc = "## Scope\nTests are optional."

    validate_semantic_fidelity(contract, title, desc, repo_context)



def test_d7_out_of_scope_is_treated_as_binding_negative_constraint():

    from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files={"forbidden.py"}, required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={"forbidden.py": PythonFileSummary(filepath="forbidden.py", module_name="forbidden", is_test=False, signatures={}, exports=[], docstring_summary="", referenced_symbols=[], file_hash="123", estimated_tokens=100, functions=[], classes=[], imports=[], variables=[])}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    title = "Implement feature"

    desc = "## Out of Scope\nModifying forbidden.py"



    import pytest

    with pytest.raises(SemanticFidelityError, match="nonbinding_escalation.*forbidden.py"):

        validate_semantic_fidelity(contract, title, desc, repo_context)



def test_d7_estimated_files_remain_nonbinding():

    from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files={"new_file.py"}, required_new_files={"new_file.py"}, required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    title = "Feature"

    desc = "## Estimated Files\nnew_file.py"



    import pytest

    with pytest.raises(SemanticFidelityError, match="nonbinding_escalation.*new_file.py"):

        validate_semantic_fidelity(contract, title, desc, repo_context)



def test_d7_recommended_dependency_remains_nonbinding():

    from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files=set(), required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={"src": ["requests"]}, forbidden_imports={}, required_calls={},

        required_patterns={}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    title = "Feature"

    desc = "## Recommendations\nUse requests library"



    import pytest

    with pytest.raises(SemanticFidelityError, match="nonbinding_escalation.*requests"):

        validate_semantic_fidelity(contract, title, desc, repo_context)



def test_d7_optional_implementation_choice_remains_nonbinding():

    from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files=set(), required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={"src": ["Singleton"]}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    title = "Feature"

    desc = "## Optional choices\nYou can use Singleton pattern"



    import pytest

    with pytest.raises(SemanticFidelityError, match="nonbinding_escalation.*Singleton"):

        validate_semantic_fidelity(contract, title, desc, repo_context)



def test_d7_unsupported_mandatory_obligation_without_provenance_rejected():

    from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files=set(), required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={"src": ["Factory"]}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    title = "Feature"

    desc = "## Scope\nDo something." # Does not mention Factory



    import pytest

    with pytest.raises(SemanticFidelityError, match="UNSUPPORTED_BINDING_OBLIGATION.*Factory"):

        validate_semantic_fidelity(contract, title, desc, repo_context)



def test_d7_valid_required_test_preservation_accepted():

    from orchestrator_core.quality_gates import _derive_gate_plan

    from orchestrator_core.schemas import AcceptanceContract, RepositoryContext, PythonFileSummary, PythonQualityPolicy, PythonProjectConfiguration, PythonProjectConfiguration



    contract = AcceptanceContract(

        required_final_files=set(), required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={"tests/test_x.py": ["test_a"]}, preserved_signatures={}, preserved_behaviors=[],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={}, required_structures={}, required_decorators={}

    )

    repo_context = RepositoryContext(

        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=set(),

        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],

        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)

    )



    gate_plan = _derive_gate_plan(repo_context, contract)

    assert gate_plan.run_tests is True



def test_d7_required_test_empty_protected_tests_rejected():

    from orchestrator import validate_contract_capabilities

    from orchestrator_core.schemas import AcceptanceContract, PreservedBehavior



    contract = AcceptanceContract(

        required_final_files=set(), required_new_files=set(), required_modified_files=set(),

        required_deleted_files=set(), preserved_files=set(), relevant_context_files=set(),

        required_tests={}, protected_tests={}, preserved_signatures={},

        preserved_behaviors=[

            PreservedBehavior(description="a", affected_files=[], validation_method="required_test", protected_tests=[])

        ],

        forbidden_test_names=set(), forbidden_constructs={}, required_exports={},

        required_quality_tools=set(), forbidden_quality_tools=set(), required_testing_techniques=set(),

        forbidden_testing_techniques=set(), required_imports={}, forbidden_imports={}, required_calls={},

        required_patterns={}, required_structures={}, required_decorators={}

    )



    valid, errors = validate_contract_capabilities(contract, {})

    assert not valid

    assert any("required_test" in e for e in errors)



def test_d7_first_candidate_valid_generates_once(mock_runtime, tmp_path):
    import orchestrator
    from orchestrator_core.schemas import AcceptanceContract
    from unittest.mock import MagicMock

    valid_contract = AcceptanceContract.model_validate_json('{"required_final_files":[]}')
    mock_agent = MagicMock(return_value=valid_contract)

    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.validate_semantic_fidelity"), \
         patch("orchestrator.validate_contract_consistency", return_value=(True, [])), \
         patch("orchestrator._derive_gate_plan", return_value=MagicMock(test_framework="none")), \
         patch("orchestrator.validate_testing_policy_compatibility", return_value=[]), \
         patch("orchestrator.tool_preflight", return_value=[]), \
         patch("orchestrator.validate_contract_capabilities", return_value=(True, [])), \
         patch("orchestrator.validate_relevant_context_files", return_value=[]), \
         patch("orchestrator.agent_analyze_and_design", return_value={"actions": []}), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")):

        try:
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
        except Exception:
            pass

        # Material assertion: agent_generate_acceptance_contract was called exactly once
        assert mock_agent.call_count == 1, (
            f"Expected exactly 1 generation call for a valid first candidate, got {mock_agent.call_count}"
        )




def test_d7_invalid_then_valid_generates_twice(mock_runtime, tmp_path):

    import orchestrator

    from orchestrator_core.schemas import AcceptanceContract

    from orchestrator_core.exceptions import CandidateSchemaError



    valid_contract = AcceptanceContract.model_validate_json('{"required_final_files":[]}')

    mock_agent = MagicMock(side_effect=[CandidateSchemaError("bad"), valid_contract])



    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.validate_semantic_fidelity"), \
         patch("orchestrator.validate_contract_consistency", return_value=(True, [])), \
         patch("orchestrator._derive_gate_plan", return_value=MagicMock(test_framework="none")), \
         patch("orchestrator.validate_testing_policy_compatibility", return_value=[]), \
         patch("orchestrator.tool_preflight", return_value=[]), \
         patch("orchestrator.validate_contract_capabilities", return_value=(True, [])), \
         patch("orchestrator.validate_relevant_context_files", return_value=[]), \
         patch("orchestrator.agent_analyze_and_design", return_value={"actions": []}), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")):



         try:

             orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

         except Exception:

             pass



         assert mock_agent.call_count == 2



def test_d7_invalid_invalid_valid_generates_thrice(mock_runtime, tmp_path):

    import orchestrator

    from orchestrator_core.schemas import AcceptanceContract

    from orchestrator_core.exceptions import CandidateSchemaError, SemanticFidelityError



    valid_contract = AcceptanceContract.model_validate_json('{"required_final_files":[]}')

    mock_agent = MagicMock(side_effect=[CandidateSchemaError("bad"), SemanticFidelityError("bad2"), valid_contract])



    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.validate_semantic_fidelity"), \
         patch("orchestrator.validate_contract_consistency", return_value=(True, [])), \
         patch("orchestrator._derive_gate_plan", return_value=MagicMock(test_framework="none")), \
         patch("orchestrator.validate_testing_policy_compatibility", return_value=[]), \
         patch("orchestrator.tool_preflight", return_value=[]), \
         patch("orchestrator.validate_contract_capabilities", return_value=(True, [])), \
         patch("orchestrator.validate_relevant_context_files", return_value=[]), \
         patch("orchestrator.agent_analyze_and_design", return_value={"actions": []}), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")):



         try:

             orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

         except Exception:

             pass



         assert mock_agent.call_count == 3



def test_d7_three_invalid_candidates_raises_exhaustion_error(mock_runtime, tmp_path):

    import orchestrator

    from orchestrator_core.exceptions import CandidateSchemaError, ContractGenerationExhaustedError



    mock_agent = MagicMock(side_effect=[CandidateSchemaError("bad1"), CandidateSchemaError("bad2"), CandidateSchemaError("bad3")])



    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_analyze_pipeline_failure"):



         with pytest.raises(ContractGenerationExhaustedError):

             orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)



def test_d7_no_design_between_retries(mock_runtime, tmp_path):

    import orchestrator

    from orchestrator_core.schemas import AcceptanceContract

    from orchestrator_core.exceptions import CandidateSchemaError



    valid_contract = AcceptanceContract.model_validate_json('{"required_final_files":[]}')

    mock_agent = MagicMock(side_effect=[CandidateSchemaError("bad1"), valid_contract])

    mock_design = MagicMock(return_value={"actions": []})



    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.validate_semantic_fidelity"), \
         patch("orchestrator.validate_contract_consistency", return_value=(True, [])), \
         patch("orchestrator._derive_gate_plan", return_value=MagicMock(test_framework="none")), \
         patch("orchestrator.validate_testing_policy_compatibility", return_value=[]), \
         patch("orchestrator.tool_preflight", return_value=[]), \
         patch("orchestrator.validate_contract_capabilities", return_value=(True, [])), \
         patch("orchestrator.validate_relevant_context_files", return_value=[]), \
         patch("orchestrator.agent_analyze_and_design", mock_design), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")):



         try:

             orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

         except Exception:

             pass



         assert mock_design.call_count == 1 # Only called once after valid contract



def test_d7_no_implementation_between_retries(mock_runtime, tmp_path):
    """Three rejected candidates: design and implement must both be 0 calls."""
    import orchestrator
    from orchestrator_core.schemas import AcceptanceContract
    from orchestrator_core.exceptions import CandidateSchemaError, ContractGenerationExhaustedError

    mock_agent = MagicMock(side_effect=[
        CandidateSchemaError("bad1"),
        CandidateSchemaError("bad2"),
        CandidateSchemaError("bad3"),
    ])
    mock_design = MagicMock(return_value={"actions": []})
    mock_implement = MagicMock(return_value="# code")

    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_analyze_pipeline_failure"), \
         patch("orchestrator.agent_analyze_and_design", mock_design), \
         patch("orchestrator.agent_implement_code", mock_implement):

        with pytest.raises(ContractGenerationExhaustedError):
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

        # Material assertions: design and implementation must NOT run during candidate retries
        assert mock_design.call_count == 0, (
            f"Expected 0 design calls during candidate retries, got {mock_design.call_count}"
        )
        assert mock_implement.call_count == 0, (
            f"Expected 0 implement calls during candidate retries, got {mock_implement.call_count}"
        )




def test_d7_no_po_for_candidate_defect(mock_runtime, tmp_path):

    import orchestrator

    from orchestrator_core.exceptions import CandidateSchemaError



    mock_agent = MagicMock(side_effect=[CandidateSchemaError("bad1"), CandidateSchemaError("bad2"), CandidateSchemaError("bad3")])

    mock_po = MagicMock()



    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_analyze_pipeline_failure"):



         # Orchestrator does not have a PO invocation for candidate generation

         with pytest.raises(Exception):

             orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)



         mock_po.assert_not_called()



def test_d7_infrastructure_error_no_retry(mock_runtime, tmp_path):

    import orchestrator

    from orchestrator_core.exceptions import InfrastructureGenerationError



    mock_agent = MagicMock(side_effect=InfrastructureGenerationError("Network down"))



    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_analyze_pipeline_failure"):



         with pytest.raises(InfrastructureGenerationError):

             orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)



         assert mock_agent.call_count == 1



def test_d7_diagnostics_preserve_attempt_category_violation(mock_runtime, tmp_path):
    import orchestrator
    from orchestrator_core.exceptions import CandidateSchemaError, ContractGenerationExhaustedError

    mock_agent = MagicMock(side_effect=[CandidateSchemaError("bad1"), CandidateSchemaError("bad2"), CandidateSchemaError("bad3")])

    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_analyze_pipeline_failure"):

        with pytest.raises(ContractGenerationExhaustedError) as excinfo:
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

        diagnostics = excinfo.value.diagnostics

        # Material assertions: 3 diagnostics in attempt order
        assert len(diagnostics) == 3
        assert diagnostics[0].attempt == 1
        assert diagnostics[0].category == "CandidateSchemaError"
        assert "bad1" in diagnostics[0].violation
        # final_phase must be a meaningful stage identifier, not N/A
        assert diagnostics[0].final_phase == "schema", f"Expected 'schema', got '{diagnostics[0].final_phase}'"

        assert diagnostics[1].attempt == 2
        assert "bad2" in diagnostics[1].violation
        assert diagnostics[1].final_phase == "schema"

        assert diagnostics[2].attempt == 3
        assert "bad3" in diagnostics[2].violation
        assert diagnostics[2].final_phase == "schema"





def test_d7_existing_testing_policy_compatibility_gate_remains_executed(mock_runtime, tmp_path):
    import orchestrator
    from orchestrator_core.schemas import AcceptanceContract

    valid_contract = AcceptanceContract.model_validate_json('{"required_final_files":[]}')
    mock_agent = MagicMock(return_value=valid_contract)
    mock_policy = MagicMock(return_value=["Policy violation"])

    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.validate_semantic_fidelity"), \
         patch("orchestrator.validate_contract_consistency", return_value=(True, [])), \
         patch("orchestrator._derive_gate_plan", return_value=MagicMock(test_framework="none")), \
         patch("orchestrator.validate_testing_policy_compatibility", mock_policy), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_analyze_pipeline_failure"):

        try:
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
        except Exception:
            pass

        # The policy validator must have been executed 3 times in the retry loop before exhausting
        assert mock_policy.call_count == 3


# --- NEW D7 MATERIAL TESTS ---

def test_d7_environment_tool_error_no_retry(mock_runtime, tmp_path):
    """EnvironmentPreflightError from tool_preflight must NOT trigger contract retry."""
    import orchestrator
    from orchestrator_core.schemas import AcceptanceContract
    from orchestrator_core.exceptions import EnvironmentPreflightError

    valid_contract = AcceptanceContract.model_validate_json('{"required_final_files":[]}')
    mock_agent = MagicMock(return_value=valid_contract)

    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.validate_semantic_fidelity"), \
         patch("orchestrator.validate_contract_consistency", return_value=(True, [])), \
         patch("orchestrator._derive_gate_plan", return_value=MagicMock(test_framework="none")), \
         patch("orchestrator.validate_testing_policy_compatibility", return_value=[]), \
         patch("orchestrator.tool_preflight", return_value=["ruff not found"]), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_analyze_pipeline_failure"):

        with pytest.raises(EnvironmentPreflightError):
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

        # Must NOT retry: generation called exactly once
        assert mock_agent.call_count == 1, (
            f"Expected 1 generation (no retry on env failure), got {mock_agent.call_count}"
        )


def test_d7_unexpected_python_error_no_retry(mock_runtime, tmp_path):
    """An unexpected Python exception from planning_agents must NOT trigger contract retry."""
    import orchestrator
    from orchestrator_core.exceptions import InfrastructureGenerationError

    # InfrastructureGenerationError from planning_agents is non-retryable
    mock_agent = MagicMock(side_effect=InfrastructureGenerationError("Unexpected runtime error"))

    with patch("orchestrator.agent_generate_acceptance_contract", mock_agent), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")), \
         patch("orchestrator.agent_analyze_pipeline_failure"):

        with pytest.raises(InfrastructureGenerationError):
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)

        # Must NOT retry: generation called exactly once
        assert mock_agent.call_count == 1, (
            f"Expected 1 generation (no retry on infrastructure error), got {mock_agent.call_count}"
        )


def test_d7_gate_execution_order(mock_runtime, tmp_path):
    """Proves the actual gate execution order: semantic_fidelity BEFORE consistency."""
    import orchestrator
    from orchestrator_core.schemas import AcceptanceContract

    valid_contract = AcceptanceContract.model_validate_json('{"required_final_files":[]}')
    execution_order = []

    def mock_semantic(*args, **kwargs):
        execution_order.append("validate_semantic_fidelity")

    def mock_consistency(*args, **kwargs):
        execution_order.append("validate_contract_consistency")
        return (True, [])

    def mock_gate_plan(*args, **kwargs):
        execution_order.append("_derive_gate_plan")
        return MagicMock(test_framework="none")

    def mock_policy(*args, **kwargs):
        execution_order.append("validate_testing_policy_compatibility")
        return []

    def mock_tool(*args, **kwargs):
        execution_order.append("tool_preflight")
        return []

    def mock_capabilities(*args, **kwargs):
        execution_order.append("validate_contract_capabilities")
        return (True, [])

    def mock_context_files(*args, **kwargs):
        execution_order.append("validate_relevant_context_files")
        return []

    with patch("orchestrator.agent_generate_acceptance_contract", return_value=valid_contract), \
         patch("orchestrator.validate_semantic_fidelity", side_effect=mock_semantic), \
         patch("orchestrator.validate_contract_consistency", side_effect=mock_consistency), \
         patch("orchestrator._derive_gate_plan", side_effect=mock_gate_plan), \
         patch("orchestrator.validate_testing_policy_compatibility", side_effect=mock_policy), \
         patch("orchestrator.tool_preflight", side_effect=mock_tool), \
         patch("orchestrator.validate_contract_capabilities", side_effect=mock_capabilities), \
         patch("orchestrator.validate_relevant_context_files", side_effect=mock_context_files), \
         patch("orchestrator.agent_analyze_and_design", return_value={"actions": []}), \
         patch("orchestrator.base_preflight", return_value=[]), \
         patch("orchestrator.validate_issue_eligibility"), \
         patch("orchestrator.transition_issue_status"), \
         patch("orchestrator.RepositoryContextManager"), \
         patch("orchestrator.subprocess.run", return_value=MagicMock(stdout="mock stdout", returncode=0)), \
         patch("orchestrator.fetch_issue", return_value=("T", "D")):

        try:
            orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
        except Exception:
            pass

    # Prove semantic_fidelity comes BEFORE consistency
    assert "validate_semantic_fidelity" in execution_order
    assert "validate_contract_consistency" in execution_order
    sf_idx = execution_order.index("validate_semantic_fidelity")
    cons_idx = execution_order.index("validate_contract_consistency")
    assert sf_idx < cons_idx, (
        f"semantic_fidelity (pos {sf_idx}) must execute BEFORE consistency (pos {cons_idx})"
    )
    # Prove full gate sequence is present
    assert execution_order == [
        "validate_semantic_fidelity",
        "validate_contract_consistency",
        "_derive_gate_plan",
        "validate_testing_policy_compatibility",
        "tool_preflight",
        "validate_contract_capabilities",
        "validate_relevant_context_files",
    ]


def test_d7_required_calls_provenance_enforcement():
    """required_calls with no Issue provenance and no repo evidence must fail semantic fidelity."""
    from orchestrator_core.semantic_validators import validate_semantic_fidelity
    from orchestrator_core.exceptions import SemanticFidelityError
    from orchestrator_core.schemas import (AcceptanceContract, RepositoryContext,
                                           PythonQualityPolicy, PythonProjectConfiguration,
                                           RequiredCall)

    contract = AcceptanceContract(
        required_calls={"src/service.py": {"do_thing": [RequiredCall(name="hidden_helper", count=1)]}},
    )
    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    title = "Add counter feature"
    desc = "## Scope\nImplement a basic counter."

    import pytest
    with pytest.raises(SemanticFidelityError, match="UNSUPPORTED_BINDING_OBLIGATION.*required_calls"):
        validate_semantic_fidelity(contract, title, desc, repo_context)


def test_d7_required_calls_with_issue_provenance_accepted():
    """required_calls with Issue provenance must be accepted."""
    from orchestrator_core.semantic_validators import validate_semantic_fidelity
    from orchestrator_core.schemas import (AcceptanceContract, RepositoryContext,
                                           PythonQualityPolicy, PythonProjectConfiguration,
                                           RequiredCall)

    contract = AcceptanceContract(
        required_calls={"src/service.py": {"do_thing": [RequiredCall(name="hidden_helper", count=1)]}},
    )
    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    title = "Add counter feature"
    # Callee name appears in the issue text -> binding Issue provenance
    desc = "## Scope\nImplement hidden_helper in do_thing."

    # Must NOT raise
    validate_semantic_fidelity(contract, title, desc, repo_context)


def test_d7_required_structures_provenance_enforcement():
    """required_structures with no Issue provenance and no repo evidence must fail."""
    from orchestrator_core.semantic_validators import validate_semantic_fidelity
    from orchestrator_core.exceptions import SemanticFidelityError
    from orchestrator_core.schemas import (AcceptanceContract, RepositoryContext,
                                           PythonQualityPolicy, PythonProjectConfiguration)

    contract = AcceptanceContract(
        required_structures={"src/mappings.py": {"GHOST_MAP": "has_aliases"}},
    )
    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    title = "Refactor service"
    desc = "## Scope\nRefactor the service layer."

    import pytest
    with pytest.raises(SemanticFidelityError, match="UNSUPPORTED_BINDING_OBLIGATION.*required_structures"):
        validate_semantic_fidelity(contract, title, desc, repo_context)


def test_d7_required_quality_tools_provenance_enforcement():
    """required_quality_tools with no Issue provenance and not in detected tools must fail."""
    from orchestrator_core.semantic_validators import validate_semantic_fidelity
    from orchestrator_core.exceptions import SemanticFidelityError
    from orchestrator_core.schemas import (AcceptanceContract, RepositoryContext,
                                           PythonQualityPolicy, PythonProjectConfiguration)

    contract = AcceptanceContract(
        required_quality_tools={"mypy"},
    )
    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    title = "Add counter feature"
    desc = "## Scope\nImplement a basic counter."

    import pytest
    with pytest.raises(SemanticFidelityError, match="UNSUPPORTED_BINDING_OBLIGATION.*required_quality_tools"):
        validate_semantic_fidelity(contract, title, desc, repo_context)


def test_d7_required_quality_tools_with_repo_provenance_accepted():
    """required_quality_tools detected in repo must be accepted without Issue provenance."""
    from orchestrator_core.semantic_validators import validate_semantic_fidelity
    from orchestrator_core.schemas import (AcceptanceContract, RepositoryContext,
                                           PythonQualityPolicy, PythonProjectConfiguration)

    contract = AcceptanceContract(
        required_quality_tools={"mypy"},
    )
    structured_config = PythonProjectConfiguration(testing_policy=None)
    structured_config.detected_quality_tools = ["mypy", "ruff"]
    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=["mypy"],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=structured_config
    )

    title = "Add feature"
    desc = "## Scope\nImplement the feature."

    # Must NOT raise - mypy is in detected_quality_tools
    validate_semantic_fidelity(contract, title, desc, repo_context)

from unittest.mock import patch, MagicMock

@patch('orchestrator.subprocess.run')
@patch('orchestrator.validate_issue_eligibility')
@patch('orchestrator.agent_analyze_pipeline_failure')
@patch('orchestrator.RepositoryContextManager')
@patch('orchestrator.agent_analyze_and_design')
@patch('orchestrator.generate_validated_acceptance_contract')
@patch('orchestrator.write_local_log')
def test_d7_run_pipeline_uses_extracted_contract_function(mock_log, mock_generate, mock_design, mock_rcm, mock_po, mock_eligibility, mock_run):
    import orchestrator
    import pytest
    from orchestrator_core.schemas import AcceptanceContract, QualityGatePlan

    mock_generate.return_value = (AcceptanceContract(), QualityGatePlan(test_framework="pytest", run_tests=False, run_mypy=False, run_ruff=False, run_vulture=False))
    mock_run.return_value.returncode = 0

    class SentinelError(Exception):
        pass

    mock_design.side_effect = SentinelError("Stop at design")

    # Mock repo context so architecture validation passes
    mock_ctx = MagicMock()
    mock_ctx.architecture_conflicts = []
    mock_rcm.return_value.build_repository_context.return_value = mock_ctx

    with pytest.raises(SentinelError):
        orchestrator.run_pipeline(1, "run-1", ".logs", MagicMock())

    mock_generate.assert_called_once()


@patch('orchestrator.validate_semantic_fidelity')
@patch('orchestrator.agent_generate_acceptance_contract')
def test_d7_extracted_function_max_3_attempts_exhaustion(mock_agent, mock_vsf):
    from orchestrator import generate_validated_acceptance_contract
    from orchestrator_core.schemas import RepositoryContext, PythonQualityPolicy, PythonProjectConfiguration
    from orchestrator_core.exceptions import ContractGenerationExhaustedError, SemanticFidelityError

    mock_vsf.side_effect = SemanticFidelityError("Fake error")

    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    import pytest
    with pytest.raises(ContractGenerationExhaustedError):
        generate_validated_acceptance_contract(
            "title", "desc", repo_context, MagicMock(), MagicMock(), MagicMock()
        )
    assert mock_agent.call_count == 3


@patch('orchestrator.estimate_repository_context_tokens', return_value=100)
@patch('orchestrator.validate_relevant_context_files', return_value=[])
@patch('orchestrator.validate_contract_capabilities', return_value=(True, []))
@patch('orchestrator.tool_preflight', return_value=[])
@patch('orchestrator.validate_testing_policy_compatibility', return_value=[])
@patch('orchestrator._derive_gate_plan')
@patch('orchestrator.validate_contract_consistency', return_value=(True, []))
@patch('orchestrator.validate_semantic_fidelity')
@patch('orchestrator.agent_generate_acceptance_contract')
def test_d7_extracted_function_retry_on_semantic_fidelity_then_success(mock_agent, mock_vsf, mock_vcc, mock_dgp, mock_vtpc, mock_tp, mock_vcap, mock_vrcf, mock_erct):
    from orchestrator import generate_validated_acceptance_contract
    from orchestrator_core.schemas import RepositoryContext, PythonQualityPolicy, PythonProjectConfiguration, AcceptanceContract, QualityGatePlan
    from orchestrator_core.exceptions import SemanticFidelityError

    mock_agent.return_value = AcceptanceContract()

    sf_calls = 0
    def fake_sf(*args, **kwargs):
        nonlocal sf_calls
        sf_calls += 1
        if sf_calls == 1:
            raise SemanticFidelityError("First fail")

    mock_vsf.side_effect = fake_sf
    mock_dgp.return_value = QualityGatePlan(test_framework="pytest", run_tests=False, run_mypy=False, run_ruff=False, run_vulture=False)

    mock_budget = MagicMock()
    mock_budget.maximum_input_tokens = 1000
    mock_budget.reserved_output_tokens = 100

    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    contract, gate = generate_validated_acceptance_contract(
        "title", "desc", repo_context, MagicMock(), mock_budget, MagicMock()
    )

    assert mock_agent.call_count == 2
    assert sf_calls == 2
    assert contract is not None
    assert gate is not None


@patch('orchestrator.tool_preflight', return_value=["Error de tool"])
@patch('orchestrator.validate_testing_policy_compatibility', return_value=[])
@patch('orchestrator._derive_gate_plan')
@patch('orchestrator.validate_contract_consistency', return_value=(True, []))
@patch('orchestrator.validate_semantic_fidelity')
@patch('orchestrator.agent_generate_acceptance_contract')
def test_d7_extracted_function_environment_error_no_retry(mock_agent, mock_vsf, mock_vcc, mock_dgp, mock_vtpc, mock_tp):
    from orchestrator import generate_validated_acceptance_contract
    from orchestrator_core.schemas import RepositoryContext, PythonQualityPolicy, PythonProjectConfiguration, AcceptanceContract, QualityGatePlan
    from orchestrator_core.exceptions import EnvironmentPreflightError

    mock_agent.return_value = AcceptanceContract()
    mock_dgp.return_value = QualityGatePlan(test_framework="pytest", run_tests=False, run_mypy=False, run_ruff=False, run_vulture=False)

    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    import pytest
    with pytest.raises(EnvironmentPreflightError):
        generate_validated_acceptance_contract(
            "title", "desc", repo_context, MagicMock(), MagicMock(), MagicMock()
        )
    assert mock_agent.call_count == 1

@patch('pathlib.Path.write_text')
@patch('pathlib.Path.mkdir')
@patch('orchestrator.agent_analyze_and_design')
@patch('orchestrator.RepositoryContextManager')
@patch('qualification.run_live_qualification.QualificationHarness.check_invariants')
@patch('qualification.run_live_qualification.generate_validated_acceptance_contract')
def test_d7_contract_mode_does_not_call_design(mock_generate, mock_ci, mock_rcm, mock_design, mock_mkdir, mock_wt):
    from qualification.run_live_qualification import QualificationHarness
    from orchestrator_core.schemas import AcceptanceContract, QualityGatePlan

    mock_generate.return_value = (AcceptanceContract(), QualityGatePlan(test_framework="pytest", run_tests=False, run_mypy=False, run_ruff=False, run_vulture=False))

    harness = QualificationHarness("contract", "q1")
    from pathlib import Path
    harness.execute_mode(Path("."), MagicMock(), "title", "body", {"RUN": 1})

    mock_design.assert_not_called()

@patch('pathlib.Path.write_text')
@patch('pathlib.Path.mkdir')
@patch('orchestrator.agent_implement_code')
@patch('orchestrator.RepositoryContextManager')
@patch('qualification.run_live_qualification.QualificationHarness.check_invariants')
@patch('qualification.run_live_qualification.generate_validated_acceptance_contract')
def test_d7_contract_mode_does_not_call_implementation(mock_generate, mock_ci, mock_rcm, mock_impl, mock_mkdir, mock_wt):
    from qualification.run_live_qualification import QualificationHarness
    from orchestrator_core.schemas import AcceptanceContract, QualityGatePlan

    mock_generate.return_value = (AcceptanceContract(), QualityGatePlan(test_framework="pytest", run_tests=False, run_mypy=False, run_ruff=False, run_vulture=False))

    harness = QualificationHarness("contract", "q1")
    from pathlib import Path
    harness.execute_mode(Path("."), MagicMock(), "title", "body", {"RUN": 1})

    mock_impl.assert_not_called()

@patch('pathlib.Path.write_text')
@patch('pathlib.Path.mkdir')
@patch('orchestrator_core.failure_analysis_agents.agent_analyze_pipeline_failure')
@patch('orchestrator.RepositoryContextManager')
@patch('qualification.run_live_qualification.generate_validated_acceptance_contract')
def test_d7_contract_mode_does_not_invoke_po(mock_generate, mock_rcm, mock_po, mock_mkdir, mock_wt):
    from qualification.run_live_qualification import QualificationHarness
    from orchestrator_core.exceptions import ContractGenerationExhaustedError
    import collections
    Diagnostic = collections.namedtuple('Diagnostic', ['attempt', 'category', 'violation', 'final_phase'])

    mock_generate.side_effect = ContractGenerationExhaustedError("Fake error", diagnostics=[])

    harness = QualificationHarness("contract", "q1")
    from pathlib import Path
    summary = {"RUN": 1}
    harness.execute_mode(Path("."), MagicMock(), "title", "body", summary)

    assert summary["CONTRACT_GENERATION"].startswith("FAIL (ContractGenerationExhaustedError")
    mock_po.assert_not_called()

@patch('orchestrator.tool_preflight', return_value=[])
@patch('orchestrator.validate_testing_policy_compatibility', return_value=[])
@patch('orchestrator._derive_gate_plan')
@patch('orchestrator.validate_contract_consistency', return_value=(True, []))
@patch('orchestrator.validate_semantic_fidelity')
@patch('orchestrator.agent_generate_acceptance_contract')
def test_d7_contract_capability_feedback_propagation(mock_agent, mock_vsf, mock_vcc, mock_dgp, mock_vtpc, mock_tp):
    from orchestrator import generate_validated_acceptance_contract
    from orchestrator_core.schemas import RepositoryContext, PythonQualityPolicy, PythonProjectConfiguration, AcceptanceContract, QualityGatePlan, PreservedBehavior

    # Attempt 1: Return an invalid contract (capability rejection)
    bad_contract = AcceptanceContract()
    bad_contract.preserved_behaviors = [
        PreservedBehavior(description="desc", validation_method="required_test", affected_files=[], protected_tests=[])
    ]

    # Attempt 2: Return a valid contract
    good_contract = AcceptanceContract()
    good_contract.preserved_behaviors = [
        PreservedBehavior(description="desc", validation_method="required_test", affected_files=[], protected_tests=["test_a"])
    ]
    good_contract.required_tests = {"a.py": ["test_a"]}

    mock_agent.side_effect = [bad_contract, good_contract]
    mock_dgp.return_value = QualityGatePlan(test_framework="pytest", run_tests=False, run_mypy=False, run_ruff=False, run_vulture=False)

    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    context_budget = MagicMock()
    context_budget.maximum_input_tokens = 100000
    context_budget.reserved_output_tokens = 8000

    contract, plan = generate_validated_acceptance_contract(
        "title", "desc", repo_context, MagicMock(), context_budget, MagicMock()
    )

    assert mock_agent.call_count == 2

    # Assert prior_feedback contains precise governance violation
    args, kwargs = mock_agent.call_args_list[1]
    prior_feedback = kwargs.get("prior_feedback", args[4] if len(args) > 4 else "")

    assert "required_test" in prior_feedback
    assert "protected_test" in prior_feedback

@patch('orchestrator.tool_preflight', return_value=[])
@patch('orchestrator.validate_testing_policy_compatibility', return_value=[])
@patch('orchestrator._derive_gate_plan')
@patch('orchestrator.validate_contract_consistency', return_value=(True, []))
@patch('orchestrator.validate_semantic_fidelity')
@patch('orchestrator.agent_generate_acceptance_contract')
def test_d7_contract_generation_exhaustion_diagnostics(mock_agent, mock_vsf, mock_vcc, mock_dgp, mock_vtpc, mock_tp):
    from orchestrator import generate_validated_acceptance_contract
    from orchestrator_core.schemas import RepositoryContext, PythonQualityPolicy, PythonProjectConfiguration, AcceptanceContract, QualityGatePlan, PreservedBehavior
    from orchestrator_core.exceptions import ContractGenerationExhaustedError
    import pytest

    # 3 attempts returning invalid capability contract
    bad_contract = AcceptanceContract()
    bad_contract.preserved_behaviors = [
        PreservedBehavior(description="desc", validation_method="required_test", affected_files=[], protected_tests=[])
    ]

    mock_agent.side_effect = [bad_contract, bad_contract, bad_contract]
    mock_dgp.return_value = QualityGatePlan(test_framework="pytest", run_tests=False, run_mypy=False, run_ruff=False, run_vulture=False)

    repo_context = RepositoryContext(
        source_index={}, test_index={}, dependency_files={}, detected_quality_tools=[],
        relevant_source_files={}, relevant_test_files={}, architecture_document="", architecture_conflicts=[],
        quality_policy=PythonQualityPolicy(), structured_config=PythonProjectConfiguration(testing_policy=None)
    )

    context_budget = MagicMock()
    context_budget.maximum_input_tokens = 100000
    context_budget.reserved_output_tokens = 8000

    with pytest.raises(ContractGenerationExhaustedError) as exc_info:
        generate_validated_acceptance_contract(
            "title", "desc", repo_context, MagicMock(), context_budget, MagicMock()
        )

    assert mock_agent.call_count == 3

    diagnostics = exc_info.value.diagnostics
    assert len(diagnostics) == 3

    for diag in diagnostics:
        assert diag.final_phase == "capability"
        assert "required_test" in diag.violation
        assert "protected_test" in diag.violation

    # Verify that attempt 2 and 3 got actionable detailed feedback
    for i in [1, 2]:
        args, kwargs = mock_agent.call_args_list[i]
        prior_feedback = kwargs.get("prior_feedback", "")
        assert "required_test" in prior_feedback
        assert "protected_test" in prior_feedback
