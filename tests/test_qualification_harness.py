import sys
import os
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import ast

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from qualification.run_live_qualification import QualificationHarness, parse_issue_fixture, main, check_test_exists_in_ast
from orchestrator_core.schemas import AcceptanceContract, PreservedBehavior


def test_fixture_copy_does_not_mutate_template(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q1_greenfield"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "issue.md").write_text("Title:\nDummy issue\n\nBody:\nbody")
    (fixture_dir / "repo").mkdir()
    (fixture_dir / "repo" / "README.md").write_text("Dummy repo")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q1")
        (fixture_dir / "issue.md").write_text("Mutated issue")
        with pytest.raises(RuntimeError, match="Fixture was mutated"):
            harness.verify_immutability()


def test_issue_fixture_parsing():
    content = "Title:\n[Qualification Q2] Non-Binding Storage Choices\n\nBody:\nThis is a test body.\nIt spans lines."
    title, body = parse_issue_fixture(content)
    assert title == "[Qualification Q2] Non-Binding Storage Choices"
    assert body == "This is a test body.\nIt spans lines."


def test_q2_estimated_files_escalation_rejected(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q2_nonbinding"
    fixture_dir.mkdir(parents=True)
    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q2")

        contract = AcceptanceContract(
            required_final_files={"storage/schema.py"},
            protected_tests={}
        )
        summary = {}
        harness.check_invariants(contract, tmp_path, summary)
        assert summary.get("SCENARIO_VERDICT") == "FAIL"
        assert summary.get("NON_BINDING_FILES") == "FAIL"
        assert summary.get("ESTIMATED_FILE_ESCALATION") == "YES"

        contract2 = AcceptanceContract(
            required_modified_files={"storage/schema.py"},
            protected_tests={}
        )
        summary2 = {}
        harness.check_invariants(contract2, tmp_path, summary2)
        assert summary2.get("SCENARIO_VERDICT") == "FAIL"
        assert summary2.get("NON_BINDING_FILES") == "FAIL"
        assert summary2.get("ESTIMATED_FILE_ESCALATION") == "YES"

        # Lookalike test
        contract3 = AcceptanceContract(
            required_modified_files={"storage/schema.py.backup"},
            protected_tests={}
        )
        summary3 = {}
        harness.check_invariants(contract3, tmp_path, summary3)
        assert summary3.get("NON_BINDING_FILES") == "PASS"


def test_q2_recommended_pydantic_escalation_rejected(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q2_nonbinding"
    fixture_dir.mkdir(parents=True)
    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q2")

        contract = AcceptanceContract(
            required_imports={"storage/model.py": ["from pydantic import BaseModel"]},
            protected_tests={}
        )
        summary = {}
        harness.check_invariants(contract, tmp_path, summary)
        assert summary.get("SCENARIO_VERDICT") == "FAIL"
        assert summary.get("NON_BINDING_DEPENDENCIES") == "FAIL"


def test_q3_required_test_empty_protected_tests_rejected(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q3_preservation"
    fixture_dir.mkdir(parents=True)
    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q3")

        contract = AcceptanceContract(
            preserved_behaviors=[PreservedBehavior(
                description="desc",
                affected_files=["counter.py"],
                validation_method="required_test",
                protected_tests=[]
            )],
            protected_tests={}
        )
        summary = {"SCENARIO_VERDICT": "PASS"}
        harness.check_invariants(contract, tmp_path, summary)
        assert summary.get("SCENARIO_VERDICT") == "FAIL"


def test_q3_required_test_nonexistent_test_rejected(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q3_preservation"
    fixture_dir.mkdir(parents=True)
    repo_path = tmp_path / "repo"
    repo_path.mkdir(parents=True)
    tests_dir = repo_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_counter.py").write_text("def test_increment_existing_behavior():\n    pass")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q3")

        contract = AcceptanceContract(
            preserved_behaviors=[PreservedBehavior(
                description="desc",
                affected_files=["counter.py"],
                validation_method="required_test",
                protected_tests=[]
            )],
            protected_tests={"tests/test_counter.py": ["test_missing"]}
        )
        summary = {"SCENARIO_VERDICT": "PASS"}
        harness.check_invariants(contract, repo_path, summary)
        assert summary.get("SCENARIO_VERDICT") == "FAIL"


def test_q3_required_test_valid_top_level_test_accepted(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q3_preservation"
    fixture_dir.mkdir(parents=True)
    repo_path = tmp_path / "repo"
    repo_path.mkdir(parents=True)
    tests_dir = repo_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_counter.py").write_text("def test_increment_existing_behavior():\n    pass")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q3")

        contract = AcceptanceContract(
            preserved_behaviors=[PreservedBehavior(
                description="desc",
                affected_files=["counter.py"],
                validation_method="required_test",
                protected_tests=[]
            )],
            protected_tests={"tests/test_counter.py": ["test_increment_existing_behavior"]}
        )
        summary = {"SCENARIO_VERDICT": "PASS"}
        harness.check_invariants(contract, repo_path, summary)
        assert summary.get("SCENARIO_VERDICT") == "PASS"


def test_q3_required_test_valid_class_method_test_accepted(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q3_preservation"
    fixture_dir.mkdir(parents=True)
    repo_path = tmp_path / "repo"
    repo_path.mkdir(parents=True)
    tests_dir = repo_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_counter.py").write_text("class TestCounter:\n    def test_increment_existing_behavior(self):\n        pass")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q3")

        contract = AcceptanceContract(
            preserved_behaviors=[PreservedBehavior(
                description="desc",
                affected_files=["counter.py"],
                validation_method="required_test",
                protected_tests=[]
            )],
            protected_tests={"tests/test_counter.py": ["test_increment_existing_behavior"]}
        )
        summary = {"SCENARIO_VERDICT": "PASS"}
        harness.check_invariants(contract, repo_path, summary)
        assert summary.get("SCENARIO_VERDICT") == "PASS"


def test_q1_real_derive_gate_plan_usage(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q1_greenfield"
    fixture_dir.mkdir(parents=True)
    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q1")

        contract = AcceptanceContract(
            required_tests={"main.py": ["test_something"]},
            protected_tests={}
        )
        summary = {"SCENARIO_VERDICT": "PASS"}
        mock_repo_context = MagicMock()

        # Valid path
        mock_gate_plan = MagicMock()
        mock_gate_plan.run_tests = True
        mock_gate_plan.test_framework = "unittest"
        with patch("orchestrator_core.quality_gates._derive_gate_plan", return_value=mock_gate_plan):
            harness.check_invariants(contract, tmp_path, summary, mock_repo_context)
        assert summary.get("SCENARIO_VERDICT") == "PASS"

        # Invalid path (framework pytest instead of unittest)
        mock_gate_plan.test_framework = "pytest"
        with patch("orchestrator_core.quality_gates._derive_gate_plan", return_value=mock_gate_plan):
            harness.check_invariants(contract, tmp_path, summary, mock_repo_context)
        assert summary.get("SCENARIO_VERDICT") == "FAIL"


def test_temporary_git_baseline(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q1_greenfield"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "issue.md").write_text("Title:\ntitle\nBody:\nbody")
    (fixture_dir / "repo").mkdir()
    (fixture_dir / "repo" / "README.md").write_text("Dummy repo")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q1")

        with patch.object(harness, "execute_mode") as mock_exec:
            def side_effect(repo_path, runtime, title, content, summary):
                assert (repo_path / ".git").exists()
                res = subprocess.run(["git", "log", "-1", "--pretty=%B"], cwd=repo_path, capture_output=True, text=True)
                assert "Initial baseline commit" in res.stdout

            mock_exec.side_effect = side_effect
            harness.run(1)


def test_qualification_result_aggregation_fails_closed(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q1_greenfield"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "issue.md").write_text("Title:\ntitle\nBody:\nbody")
    (fixture_dir / "repo").mkdir()
    (fixture_dir / "repo" / "README.md").write_text("Dummy repo")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q1")

        with patch.object(harness, "execute_mode") as mock_exec:
            def side_effect(repo_path, runtime, title, content, summary):
                raise Exception("Simulated runtime error in pipeline")

            mock_exec.side_effect = side_effect
            summary = harness.run(1)
            assert "FAIL" in summary.get("HARNESS_EXECUTION")
            assert summary.get("SCENARIO_VERDICT") == "FAIL"


def test_main_exit_code_semantics(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q1_greenfield"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "issue.md").write_text("Title:\ntitle\nBody:\nbody")
    (fixture_dir / "repo").mkdir()
    (fixture_dir / "repo" / "README.md").write_text("Dummy repo")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        with patch("qualification.run_live_qualification.QualificationHarness.run") as mock_run:
            # Case 1: [PASS, FAIL, PASS] -> aggregate FAIL -> exit 1
            mock_run.side_effect = [
                {"HARNESS_EXECUTION": "PASS", "SCENARIO_VERDICT": "PASS"},
                {"HARNESS_EXECUTION": "PASS", "SCENARIO_VERDICT": "FAIL"},
                {"HARNESS_EXECUTION": "PASS", "SCENARIO_VERDICT": "PASS"}
            ]
            assert main(["--mode", "contract", "--scenario", "q1", "--repeat", "3"]) == 1

            # Case 2: [PASS, PASS, PASS] -> aggregate PASS -> exit 0
            mock_run.side_effect = [
                {"HARNESS_EXECUTION": "PASS", "SCENARIO_VERDICT": "PASS"},
                {"HARNESS_EXECUTION": "PASS", "SCENARIO_VERDICT": "PASS"},
                {"HARNESS_EXECUTION": "PASS", "SCENARIO_VERDICT": "PASS"}
            ]
            assert main(["--mode", "contract", "--scenario", "q1", "--repeat", "3"]) == 0

from unittest.mock import patch, MagicMock

@patch('pathlib.Path.write_text')
@patch('pathlib.Path.mkdir')
@patch('qualification.run_live_qualification.QualificationHarness.check_invariants')
@patch('orchestrator.estimate_repository_context_tokens', return_value=100)
@patch('orchestrator.tool_preflight', return_value=[])
@patch('orchestrator.agent_generate_acceptance_contract')
def test_q1_invalid_then_valid_exactly_2_generations(mock_generate, mock_tp, mock_erct, mock_ci, mock_mkdir, mock_wt):
    from qualification.run_live_qualification import QualificationHarness
    from orchestrator_core.schemas import AcceptanceContract

    contract1 = AcceptanceContract()

    contract2 = AcceptanceContract(
        required_tests={"tests/test_feature.py": ["test_feature_works"]}
    )

    mock_generate.side_effect = [contract1, contract2]

    harness = QualificationHarness("contract", "q1")
    summary = {"RUN": 1}
    from pathlib import Path
    harness.execute_mode(Path("."), MagicMock(), "Automated tests cover the behavior.", "Automated tests cover the behavior.", summary)

    assert mock_generate.call_count == 2
    assert summary["CONTRACT_GENERATION"] == "PASS"

@patch('pathlib.Path.write_text')
@patch('pathlib.Path.mkdir')
@patch('orchestrator.tool_preflight', return_value=[])
@patch('orchestrator.agent_generate_acceptance_contract')
def test_q1_three_invalid_exhaustion_exactly_3_generations(mock_generate, mock_tp, mock_mkdir, mock_wt):
    from qualification.run_live_qualification import QualificationHarness
    from orchestrator_core.schemas import AcceptanceContract

    contract_invalid = AcceptanceContract()

    mock_generate.side_effect = [contract_invalid, contract_invalid, contract_invalid]

    harness = QualificationHarness("contract", "q1")
    summary = {"RUN": 1}
    from pathlib import Path
    harness.execute_mode(Path("."), MagicMock(), "Automated tests cover the behavior.", "Automated tests cover the behavior.", summary)

    assert mock_generate.call_count == 3
    assert summary["CONTRACT_GENERATION"].startswith("FAIL (ContractGenerationExhaustedError")

@patch('pathlib.Path.write_text')
@patch('pathlib.Path.mkdir')
@patch('qualification.run_live_qualification.QualificationHarness.check_invariants')
@patch('orchestrator.estimate_repository_context_tokens', return_value=100)
@patch('orchestrator.tool_preflight', return_value=[])
@patch('orchestrator.agent_generate_acceptance_contract')
def test_q2_governance_invalid_then_valid_exactly_2_generations(mock_generate, mock_tp, mock_erct, mock_ci, mock_mkdir, mock_wt):
    from qualification.run_live_qualification import QualificationHarness
    from orchestrator_core.schemas import AcceptanceContract, PreservedBehavior

    contract_invalid = AcceptanceContract(
        preserved_behaviors=[PreservedBehavior(description="foo", affected_files=[], validation_method="required_test", protected_tests=[])],
        required_tests={"tests/test_feature.py": ["test_feature_works"]}
    )

    contract_valid = AcceptanceContract(
        preserved_behaviors=[PreservedBehavior(description="foo", affected_files=[], validation_method="required_test", protected_tests=["test_feature_works"])],
        required_tests={"tests/test_feature.py": ["test_feature_works"]}
    )

    mock_generate.side_effect = [contract_invalid, contract_valid]

    harness = QualificationHarness("contract", "q2")
    summary = {"RUN": 1}
    from pathlib import Path
    harness.execute_mode(Path("."), MagicMock(), "Automated tests cover the behavior.", "Automated tests cover the behavior.", summary)

    assert mock_generate.call_count == 2
    assert summary["CONTRACT_GENERATION"] == "PASS"

@patch('pathlib.Path.write_text')
@patch('pathlib.Path.mkdir')
@patch('orchestrator.tool_preflight', return_value=["Error infra"])
@patch('orchestrator.agent_generate_acceptance_contract')
def test_infrastructure_failure_no_retry_exactly_1_generation(mock_generate, mock_tp, mock_mkdir, mock_wt):
    from qualification.run_live_qualification import QualificationHarness
    from orchestrator_core.schemas import AcceptanceContract

    contract = AcceptanceContract(
        required_tests={"tests/test_feature.py": ["test_feature_works"]}
    )

    mock_generate.return_value = contract

    harness = QualificationHarness("contract", "q1")
    summary = {"RUN": 1}
    from pathlib import Path
    harness.execute_mode(Path("."), MagicMock(), "Automated tests cover the behavior.", "Automated tests cover the behavior.", summary)

    assert mock_generate.call_count == 1
    assert summary["CONTRACT_GENERATION"].startswith("FAIL (PROVIDER/INFRASTRUCTURE:")

def test_e2e_silent_pipeline_failure_fails_closed(tmp_path):
    import subprocess
    from qualification.run_live_qualification import QualificationHarness
    fixture_dir = tmp_path / "fixtures" / "q1_greenfield"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "issue.md").write_text("Title:\ntitle\nBody:\nbody")
    (fixture_dir / "repo").mkdir()
    (fixture_dir / "repo" / "README.md").write_text("Dummy repo")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("e2e", "q1")

        with patch("qualification.run_live_qualification.run_pipeline") as mock_rp:
            repo_path = fixture_dir / "repo"
            subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "add", "README.md"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial baseline commit"], cwd=repo_path, capture_output=True)

            summary = {"RUN": 1, "HARNESS_EXECUTION": "PASS"}
            harness.execute_mode(repo_path, MagicMock(), "title", "body", summary)

            assert summary.get("HARNESS_EXECUTION") == "PASS"
            assert summary.get("TEMP_REPO_BASELINE_HEAD") == summary.get("TEMP_REPO_FINAL_HEAD")
            assert summary.get("SCENARIO_VERDICT") == "FAIL"

def test_e2e_success_signal_passes(tmp_path):
    import subprocess
    from qualification.run_live_qualification import QualificationHarness
    fixture_dir = tmp_path / "fixtures" / "q1_greenfield"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "issue.md").write_text("Title:\ntitle\nBody:\nbody")
    (fixture_dir / "repo").mkdir()
    (fixture_dir / "repo" / "README.md").write_text("Dummy repo")

    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("e2e", "q1")

        def mock_run_pipeline(issue_id, run_id, log_dir, runtime):
            repo_path = fixture_dir / "repo"
            (repo_path / "main.py").write_text("print('hello')")
            subprocess.run(["git", "add", "main.py"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Pipeline success"], cwd=repo_path, capture_output=True)

        with patch("qualification.run_live_qualification.run_pipeline", side_effect=mock_run_pipeline):
            repo_path = fixture_dir / "repo"
            subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "add", "README.md"], cwd=repo_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Initial baseline commit"], cwd=repo_path, capture_output=True)

            summary = {"RUN": 1, "HARNESS_EXECUTION": "PASS"}
            harness.execute_mode(repo_path, MagicMock(), "title", "body", summary)

            assert summary.get("HARNESS_EXECUTION") == "PASS"
            assert summary.get("TEMP_REPO_BASELINE_HEAD") != summary.get("TEMP_REPO_FINAL_HEAD")
            assert summary.get("SCENARIO_VERDICT") == "PASS"
