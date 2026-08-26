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
        summary = {}
        harness.check_invariants(contract, tmp_path, summary)
        assert summary.get("SCENARIO_VERDICT") == "FAIL"


def test_q3_required_test_nonexistent_test_rejected(tmp_path):
    fixture_dir = tmp_path / "fixtures" / "q3_preservation"
    fixture_dir.mkdir(parents=True)
    with patch("qualification.run_live_qualification.get_fixture_path", return_value=fixture_dir):
        harness = QualificationHarness("contract", "q3")

        contract = AcceptanceContract(
            preserved_behaviors=[PreservedBehavior(
                description="desc",
                affected_files=["counter.py"],
                validation_method="required_test",
                protected_tests=["tests/test_counter.py::test_missing"]
            )],
            protected_tests={}
        )
        summary = {}
        harness.check_invariants(contract, tmp_path, summary)
        assert summary.get("SCENARIO_VERDICT") == "FAIL"


def test_q3_required_test_valid_protected_test_accepted(tmp_path):
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
                protected_tests=["tests/test_counter.py::TestCounter::test_increment_existing_behavior"]
            )],
            protected_tests={}
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
