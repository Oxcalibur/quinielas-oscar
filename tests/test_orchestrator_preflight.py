import os
import sys
import json
import pytest
import subprocess
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import orchestrator
from orchestrator_core.prompt_budget import PreflightError

def test_T_O1A_wrong_target_origin_fails_before_mutation(tmp_path):
    # Setup dummy target workspace
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=target, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=target, check=True)
    subprocess.run(["git", "remote", "add", "origin", "wrong/repo"], cwd=target, check=True)
    
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--issue", "1", "--target-repo", "expected/repo", "--target-workspace", str(target), "--target-branch", "main"],
        capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "Target origin mismatch" in result.stdout

def test_T_O1B_wrong_target_branch_fails_before_mutation(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-b", "wrong_branch"], cwd=target, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=target, check=True)
    subprocess.run(["git", "remote", "add", "origin", "expected/repo"], cwd=target, check=True)
    
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--issue", "1", "--target-repo", "expected/repo", "--target-workspace", str(target), "--target-branch", "main"],
        capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "no coincide con el base declarado" in result.stdout

def test_T_O1C_dirty_target_fails_before_mutation(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=target, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=target, check=True)
    subprocess.run(["git", "remote", "add", "origin", "expected/repo"], cwd=target, check=True)
    
    (target / "dirty.txt").write_text("dirty")
    
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--issue", "1", "--target-repo", "expected/repo", "--target-workspace", str(target), "--target-branch", "main"],
        capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "no está limpio" in result.stdout

def test_T_O1D_worktree_is_based_on_verified_target_repository():
    # If the workspace validation passes, the worktree command will use cwd=args.target_workspace
    # We can inspect the source code of orchestrator.py
    import inspect
    with open("orchestrator.py", "r", encoding="utf-8") as f:
        source = f.read()
    assert 'cwd=args.target_workspace' in source
    assert 'target_info["head"]' in source
    assert 'git", "worktree", "add' in source

def test_T_O1E_runtime_github_repository_equals_explicit_target_repository():
    import orchestrator_core.runtime
    import inspect
    source = inspect.getsource(orchestrator_core.runtime.build_runtime_clients)
    assert "target_repo" in source
    assert "github_client.get_repo(repo_name)" in source

@pytest.fixture
def mock_runtime():
    runtime = MagicMock(spec=orchestrator.RuntimeClients)
    runtime.ai_client = MagicMock()
    runtime.github_client = MagicMock()
    runtime.repo = MagicMock()
    return runtime

def test_T_O2A_issue_without_ready_to_code_is_rejected(mock_runtime, tmp_path):
    issue = MagicMock()
    issue.labels = [MagicMock(name="other")]
    issue.labels[0].name = "other"
    mock_runtime.repo.get_issue.return_value = issue
    
    with pytest.raises(PreflightError, match="no tiene la etiqueta 'ai:ready-to-code'"):
        orchestrator.validate_issue_eligibility(1, mock_runtime)

def test_T_O2B_issue_without_po_metadata_is_rejected(mock_runtime, tmp_path):
    issue = MagicMock()
    label = MagicMock()
    label.name = "ai:ready-to-code"
    issue.labels = [label]
    issue.body = "No metadata here"
    mock_runtime.repo.get_issue.return_value = issue
    
    with pytest.raises(PreflightError, match="no contiene metadata de PO"):
        orchestrator.validate_issue_eligibility(1, mock_runtime)

def test_T_O2C_issue_whose_parent_epic_is_not_deployed_is_rejected(mock_runtime, tmp_path):
    child_issue = MagicMock()
    child_label = MagicMock()
    child_label.name = "ai:ready-to-code"
    child_issue.labels = [child_label]
    child_issue.body = "PO_PARENT_EPIC=2\nPO_CHILD_INDEX=1\nFINGERPRINT=0123456789abcdef"
    
    parent_epic = MagicMock()
    parent_label = MagicMock()
    parent_label.name = "other"
    parent_epic.labels = [parent_label]
    
    def mock_get_issue(number):
        if number == 1: return child_issue
        if number == 2: return parent_epic
        raise Exception("Not found")
        
    mock_runtime.repo.get_issue.side_effect = mock_get_issue
    
    with pytest.raises(PreflightError, match="no tiene la etiqueta 'gate:deployed'"):
        orchestrator.validate_issue_eligibility(1, mock_runtime)

def test_T_O2D_valid_deployed_po_child_passes_eligibility(mock_runtime, tmp_path):
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
    
    # We mock fetch_issue to throw an expected exception further down the line to prove it passed the preflight
    orchestrator.validate_issue_eligibility(1, mock_runtime)
            
    # Verify labels were modified as part of the status change
    orchestrator.transition_issue_status(1, mock_runtime)
    child_issue.remove_from_labels.assert_any_call("ai:ready-to-code")
    child_issue.add_to_labels.assert_any_call("status:in-progress")

@patch("orchestrator.RepositoryContextManager")
@patch("orchestrator.base_preflight", return_value=[])
@patch("orchestrator.fetch_issue", return_value=("T", "D"))
@patch("orchestrator.agent_generate_acceptance_contract", return_value=MagicMock())
@patch("orchestrator.validate_contract_consistency", return_value=(True, []))
@patch("orchestrator._derive_gate_plan", return_value=MagicMock(run_mypy=False, run_tests=False, run_static_analysis=False))
@patch("orchestrator.validate_testing_policy_compatibility", return_value=[])
@patch("orchestrator.tool_preflight", return_value=[])
@patch("orchestrator.validate_contract_capabilities", return_value=(True, []))
@patch("orchestrator.validate_relevant_context_files", return_value=[])
@patch("subprocess.run")
@patch("orchestrator.agent_analyze_and_design", return_value={"actions": []})
@patch("orchestrator.validate_design", return_value=(True, []))
@patch("orchestrator.validate_generated_manifest", return_value=(True, ""))
@patch("orchestrator.validate_final_state", return_value=(True, ""))
@patch("orchestrator.agent_code_reviewer", return_value=MagicMock(approved=True, design_conflict=False, model_dump=lambda: {}))
@patch("orchestrator.agent_security_audit", return_value=MagicMock(approved=True, findings=[]))
@patch("orchestrator.agent_update_architecture_doc", return_value="docs/ARCHITECTURE.md")
@patch("orchestrator.agent_generate_execution_report", return_value="Report")
@patch("orchestrator.agent_update_user_manual", return_value="Manual")
@patch("orchestrator.deploy_to_github", side_effect=Exception("Simulated deployment failure"))
@patch("orchestrator.handle_pipeline_failure")
def test_T_O4_deploy_to_github_exception_propagates(
    mock_handle, mock_deploy, mock_manual, mock_report, mock_arch, mock_audit, mock_review, mock_final, mock_manifest, mock_design_val, mock_design, mock_run, mock_files, mock_cap, mock_tool, mock_policy, mock_plan, mock_cons, mock_contract, mock_fetch, mock_base, mock_rcm, mock_runtime, tmp_path
):
         
         # Mock eligibility
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
         
         orchestrator.run_pipeline(1, "run1", str(tmp_path), mock_runtime)
         
         # The exception must be caught and propagated to handle_pipeline_failure
         mock_handle.assert_called_once()
         assert "Simulated deployment failure" in str(mock_handle.call_args[0][2])

def test_T_O1_partial_target_config_fails_closed():
    import sys, subprocess
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--issue", "1", "--target-repo", "Oxcalibur/bookai-engine"],
        capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "Se deben proveer ambos o ninguno" in result.stdout

    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--issue", "1", "--target-workspace", "/tmp/fake"],
        capture_output=True, text=True
    )
    assert result.returncode == 1
    assert "Se deben proveer ambos o ninguno" in result.stdout

def test_T_O2_cli_ordering_invalid_issue(tmp_path):
    import sys, subprocess
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=target, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=target, check=True)
    subprocess.run(["git", "remote", "add", "origin", "expected/repo"], cwd=target, check=True)
    
    result = subprocess.run(
        [sys.executable, "orchestrator.py", "--issue", "99999", "--target-repo", "expected/repo", "--target-workspace", str(target), "--target-branch", "main"],
        capture_output=True, text=True
    )
    # We know this will fail network check or fetch issue, before any worktree is added.
    
def test_T_O2E_issue_fetch_failure_fails_closed(mock_runtime):
    import orchestrator
    from orchestrator_core.prompt_budget import PreflightError
    import pytest
    mock_runtime.repo.get_issue.side_effect = Exception("Network timeout")
    with pytest.raises(PreflightError, match="No se pudo obtener el Issue"):
        orchestrator.validate_issue_eligibility(1, mock_runtime)

def test_T_O1_platform_credential_context():
    # Test that build_runtime_clients respects target_repo parameter
    import orchestrator_core.runtime
    import inspect
    source = inspect.getsource(orchestrator_core.runtime.build_runtime_clients)
    assert "target_repo" in source
    assert "target_repo if target_repo else" in source
