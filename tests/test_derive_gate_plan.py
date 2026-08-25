import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add the project root to sys.path to import orchestrator
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock environment variables and Github client before importing orchestrator
os.environ["GITHUB_TOKEN"] = "fake_token"
os.environ["REPO_OWNER"] = "fake_owner"
os.environ["REPO_NAME"] = "fake_repo"
os.environ["GEMINI_API_KEY"] = "fake_key"

with patch("github.Github") as mock_github:
    from orchestrator import _derive_gate_plan, PreflightError, resolve_mocking_instruction, FileContract


class TestDeriveGatePlan(unittest.TestCase):
    def setUp(self):
        self.repo_context_mock = MagicMock()
        self.repo_context_mock.structured_config.mypy_enabled = False
        self.repo_context_mock.structured_config.detected_quality_tools = []
        self.repo_context_mock.structured_config.ruff_enabled = False
        self.repo_context_mock.structured_config.vulture_enabled = False
        
        self.contract_mock = MagicMock()
        self.contract_mock.required_tests = {}
        self.contract_mock.protected_tests = {}
        self.contract_mock.required_testing_techniques = []
        self.contract_mock.forbidden_testing_techniques = []
        self.contract_mock.required_quality_tools = []
        self.contract_mock.forbidden_quality_tools = []

    def test_1_repo_unittest_required_pytest(self):
        # repo_detected = "unittest", required = {"pytest"} -> expected: pytest, True
        self.repo_context_mock.detected_test_framework = "unittest"
        self.contract_mock.required_quality_tools = ["pytest"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        
        self.assertEqual(plan.test_framework, "pytest")
        self.assertTrue(plan.run_tests)

    def test_2_repo_pytest_required_unittest(self):
        # repo_detected = "pytest", required = {"unittest"} -> expected: unittest, True
        self.repo_context_mock.detected_test_framework = "pytest"
        self.contract_mock.required_quality_tools = ["unittest"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        
        self.assertEqual(plan.test_framework, "unittest")
        self.assertTrue(plan.run_tests)

    def test_3_required_unittest_forbidden_pytest(self):
        # required = {"unittest"}, forbidden = {"pytest"} -> expected: unittest, True
        self.repo_context_mock.detected_test_framework = "pytest" # Doesn't matter
        self.contract_mock.required_quality_tools = ["unittest"]
        self.contract_mock.forbidden_quality_tools = ["pytest"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        
        self.assertEqual(plan.test_framework, "unittest")
        self.assertTrue(plan.run_tests)

    def test_4_required_pytest_forbidden_unittest(self):
        # required = {"pytest"}, forbidden = {"unittest"} -> expected: pytest, True
        self.repo_context_mock.detected_test_framework = "unittest" # Doesn't matter
        self.contract_mock.required_quality_tools = ["pytest"]
        self.contract_mock.forbidden_quality_tools = ["unittest"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        
        self.assertEqual(plan.test_framework, "pytest")
        self.assertTrue(plan.run_tests)

    def test_5_required_pytest_and_unittest_fails_contract_validation(self):
        # required = {"pytest", "unittest"} -> expected: fails in validate_contract_capabilities, 
        # but _derive_gate_plan doesn't check mutual exclusivity (done earlier), 
        # but it will pick one (pytest usually as explicit_framework is "pytest" first, 
        # but let's test validate_contract_capabilities)
        from orchestrator import validate_contract_capabilities, AcceptanceContract
        
        contract = AcceptanceContract(
            required_quality_tools=["pytest", "unittest"],
            title="Test",
            description="Test",
            file_contracts=[],
            required_tests={},
            protected_tests={},
            forbidden_test_names=[],
            preserved_signatures={},
            preserved_behaviors=[],
            required_exports={},
            required_imports={},
            forbidden_imports={},
            required_patterns={},
            required_calls={},
            required_structures={},
            required_decorators={},
            required_testing_techniques=[],
            forbidden_testing_techniques=[],
            forbidden_constructs={},
            relevant_context_files=[],
            forbidden_quality_tools=[]
        )
        # Assuming _validator_registry is available or we pass empty for basic checks
        valid, errors = validate_contract_capabilities(contract, {})
        self.assertFalse(valid)
        self.assertTrue(any("simultáneamente" in err for err in errors))

    def test_6_repo_pytest_forbidden_pytest_requires_tests_fails(self):
        # repo_detected = "pytest", forbidden = {"pytest"}, required_tests = {"a": ["b"]} -> expected: PreflightError
        self.repo_context_mock.detected_test_framework = "pytest"
        self.contract_mock.forbidden_quality_tools = ["pytest"]
        self.contract_mock.required_tests = {"tests/test_example.py": ["test_example"]}
        
        with self.assertRaises(PreflightError) as context:
            _derive_gate_plan(self.repo_context_mock, self.contract_mock)
            
        self.assertIn("exige pruebas", str(context.exception))
        self.assertIn("permitido", str(context.exception))

    def test_7_repo_pytest_forbidden_pytest_no_required_tests_succeeds(self):
        # repo_detected = "pytest", forbidden = {"pytest"}, required_tests = {} -> expected: run_tests=False, test_framework="none"
        self.repo_context_mock.detected_test_framework = "pytest"
        self.contract_mock.forbidden_quality_tools = ["pytest"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        self.assertFalse(plan.run_tests)
        self.assertEqual(plan.test_framework, "none")

    def test_8_resolve_mocking_instruction_unittest(self):
        file_contract = MagicMock()
        repo_context = MagicMock()
        repo_context.detected_mocking_instruction = "Usa pytest-mock (mocker)."
        
        instruction = resolve_mocking_instruction("unittest", file_contract, repo_context)
        self.assertEqual(instruction, "Usa unittest.mock.patch para aislar dependencias.")

    def test_9_resolve_mocking_instruction_pytest_with_required(self):
        file_contract = MagicMock()
        file_contract.required_testing_techniques = ["pytest-mock"]
        repo_context = MagicMock()
        
        instruction = resolve_mocking_instruction("pytest", file_contract, repo_context)
        self.assertEqual(instruction, "Usa pytest-mock mediante el fixture mocker.")

    def test_10_resolve_mocking_instruction_pytest_repo_detected_compatible(self):
        file_contract = MagicMock()
        file_contract.required_testing_techniques = []
        file_contract.forbidden_testing_techniques = ["monkeypatch"]
        repo_context = MagicMock()
        
        instruction = resolve_mocking_instruction("pytest", file_contract, repo_context)
        self.assertEqual(instruction, "Usa pytest-mock mediante el fixture mocker para aislar dependencias.")

    def test_11_resolve_mocking_instruction_pytest_repo_detected_incompatible(self):
        file_contract = MagicMock()
        file_contract.required_testing_techniques = []
        file_contract.forbidden_testing_techniques = ["mocker", "pytest-mock"]
        repo_context = MagicMock()
        
        instruction = resolve_mocking_instruction("pytest", file_contract, repo_context)
        self.assertEqual(instruction, "Usa el fixture monkeypatch para aislar dependencias.")

    def test_12_required_mocker_forbidden_pytest_mock_fails(self):
        # Alias contradictorios
        from orchestrator import validate_contract_capabilities, AcceptanceContract
        contract = AcceptanceContract(
            required_quality_tools=[],
            title="Test",
            description="Test",
            file_contracts=[],
            required_tests={},
            protected_tests={},
            forbidden_test_names=[],
            preserved_signatures={},
            preserved_behaviors=[],
            required_exports={},
            required_imports={},
            forbidden_imports={},
            required_patterns={},
            required_calls={},
            required_structures={},
            required_decorators={},
            required_testing_techniques=["mocker"],
            forbidden_testing_techniques=["pytest-mock"],
            forbidden_constructs={},
            relevant_context_files=[],
            forbidden_quality_tools=[]
        )
        valid, errors = validate_contract_capabilities(contract, {})
        self.assertFalse(valid)
        self.assertTrue(any("required y forbidden al mismo tiempo" in err for err in errors))

    def test_13_required_pytest_mock_forbidden_mocker_fails(self):
        # Alias contradictorios
        from orchestrator import validate_contract_capabilities, AcceptanceContract
        contract = AcceptanceContract(
            required_quality_tools=[],
            title="Test",
            description="Test",
            file_contracts=[],
            required_tests={},
            protected_tests={},
            forbidden_test_names=[],
            preserved_signatures={},
            preserved_behaviors=[],
            required_exports={},
            required_imports={},
            forbidden_imports={},
            required_patterns={},
            required_calls={},
            required_structures={},
            required_decorators={},
            required_testing_techniques=["pytest-mock"],
            forbidden_testing_techniques=["mocker"],
            forbidden_constructs={},
            relevant_context_files=[],
            forbidden_quality_tools=[]
        )
        valid, errors = validate_contract_capabilities(contract, {})
        self.assertFalse(valid)
        self.assertTrue(any("required y forbidden al mismo tiempo" in err for err in errors))

    def test_14_required_monkeypatch_forbidden_monkeypatch_fails(self):
        # Igualdad directa
        from orchestrator import validate_contract_capabilities, AcceptanceContract
        contract = AcceptanceContract(
            required_quality_tools=[],
            title="Test",
            description="Test",
            file_contracts=[],
            required_tests={},
            protected_tests={},
            forbidden_test_names=[],
            preserved_signatures={},
            preserved_behaviors=[],
            required_exports={},
            required_imports={},
            forbidden_imports={},
            required_patterns={},
            required_calls={},
            required_structures={},
            required_decorators={},
            required_testing_techniques=["monkeypatch"],
            forbidden_testing_techniques=["monkeypatch"],
            forbidden_constructs={},
            relevant_context_files=[],
            forbidden_quality_tools=[]
        )
        valid, errors = validate_contract_capabilities(contract, {})
        self.assertFalse(valid)
        self.assertTrue(any("required y forbidden al mismo tiempo" in err for err in errors))

    def test_15_unittest_required_mocker_fails(self):
        # unittest incompatible
        from orchestrator import validate_contract_capabilities, AcceptanceContract
        contract = AcceptanceContract(
            required_quality_tools=["unittest"],
            title="Test",
            description="Test",
            file_contracts=[],
            required_tests={},
            protected_tests={},
            forbidden_test_names=[],
            preserved_signatures={},
            preserved_behaviors=[],
            required_exports={},
            required_imports={},
            forbidden_imports={},
            required_patterns={},
            required_calls={},
            required_structures={},
            required_decorators={},
            required_testing_techniques=["mocker"],
            forbidden_testing_techniques=[],
            forbidden_constructs={},
            relevant_context_files=[],
            forbidden_quality_tools=[]
        )
        valid, errors = validate_contract_capabilities(contract, {})
        self.assertFalse(valid)
        self.assertTrue(any("requiere 'unittest' pero también exige técnicas incompatibles" in err for err in errors))

    def test_16_unittest_required_pytest_mock_fails(self):
        # unittest incompatible
        from orchestrator import validate_contract_capabilities, AcceptanceContract
        contract = AcceptanceContract(
            required_quality_tools=["unittest"],
            title="Test",
            description="Test",
            file_contracts=[],
            required_tests={},
            protected_tests={},
            forbidden_test_names=[],
            preserved_signatures={},
            preserved_behaviors=[],
            required_exports={},
            required_imports={},
            forbidden_imports={},
            required_patterns={},
            required_calls={},
            required_structures={},
            required_decorators={},
            required_testing_techniques=["pytest-mock"],
            forbidden_testing_techniques=[],
            forbidden_constructs={},
            relevant_context_files=[],
            forbidden_quality_tools=[]
        )
        valid, errors = validate_contract_capabilities(contract, {})
        self.assertFalse(valid)
        self.assertTrue(any("requiere 'unittest' pero también exige técnicas incompatibles" in err for err in errors))

    def test_17_unittest_required_unittest_mock_patch_succeeds(self):
        # unittest incompatible con mocker/pytest-mock, compatible con unittest.mock.patch
        from orchestrator import validate_contract_capabilities, AcceptanceContract, _validator_registry
        contract = AcceptanceContract(
            required_quality_tools=["unittest"],
            title="Test",
            description="Test",
            file_contracts=[],
            required_tests={},
            protected_tests={},
            forbidden_test_names=[],
            preserved_signatures={},
            preserved_behaviors=[],
            required_exports={},
            required_imports={},
            forbidden_imports={},
            required_patterns={},
            required_calls={},
            required_structures={},
            required_decorators={},
            required_testing_techniques=["unittest.mock.patch"],
            forbidden_testing_techniques=[],
            forbidden_constructs={},
            relevant_context_files=[],
            forbidden_quality_tools=[]
        )
        valid, errors = validate_contract_capabilities(contract, _validator_registry)
        self.assertTrue(valid, f"Expected valid contract, got errors: {errors}")
        self.assertEqual(len(errors), 0)

    def test_18_resolve_mocking_instruction_pytest_required_mocker(self):
        file_contract = MagicMock()
        file_contract.required_testing_techniques = ["mocker"]
        file_contract.forbidden_testing_techniques = []
        repo_context = MagicMock()
        
        instruction = resolve_mocking_instruction("pytest", file_contract, repo_context)
        self.assertEqual(instruction, "Usa pytest-mock mediante el fixture mocker.")

        self.assertEqual(instruction, "Usa pytest-mock mediante el fixture mocker.")

    def test_19_repo_unittest_required_monkeypatch_yields_pytest(self):
        # 1. repo_framework = "unittest", required_testing_techniques = {"monkeypatch"} -> pytest, True
        self.repo_context_mock.detected_test_framework = "unittest"
        self.contract_mock.required_testing_techniques = ["monkeypatch"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        self.assertEqual(plan.test_framework, "pytest")
        self.assertTrue(plan.run_tests)

    def test_20_repo_unittest_required_mocker_yields_pytest(self):
        # 2. repo_framework = "unittest", required_testing_techniques = {"mocker"} -> pytest
        self.repo_context_mock.detected_test_framework = "unittest"
        self.contract_mock.required_testing_techniques = ["mocker"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        self.assertEqual(plan.test_framework, "pytest")
        self.assertTrue(plan.run_tests)

    def test_21_forbidden_pytest_required_monkeypatch_fails(self):
        # 5. forbidden_quality_tools = {"pytest"}, required_testing_techniques = {"monkeypatch"} -> fails
        self.repo_context_mock.detected_test_framework = "unittest"
        self.contract_mock.forbidden_quality_tools = ["pytest"]
        self.contract_mock.required_testing_techniques = ["monkeypatch"]
        
        with self.assertRaises(PreflightError) as context:
            _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        self.assertIn("prohibido", str(context.exception))
        self.assertIn("pytest", str(context.exception))

    def test_22_repo_pytest_required_unittest_mock_patch_yields_pytest(self):
        # 7. repo_framework = "pytest", required_testing_techniques = {"unittest.mock.patch"} -> pytest
        self.repo_context_mock.detected_test_framework = "pytest"
        self.contract_mock.required_testing_techniques = ["unittest.mock.patch"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        self.assertEqual(plan.test_framework, "pytest")
        self.assertTrue(plan.run_tests)

    def test_23_repo_unittest_required_unittest_mock_patch_yields_unittest(self):
        # 8. repo_framework = "unittest", required_testing_techniques = {"unittest.mock.patch"} -> unittest
        self.repo_context_mock.detected_test_framework = "unittest"
        self.contract_mock.required_testing_techniques = ["unittest.mock.patch"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        self.assertEqual(plan.test_framework, "unittest")
        self.assertTrue(plan.run_tests)

    def test_24_repo_none_required_monkeypatch_yields_pytest(self):
        # 9. repo_framework = None, required_testing_techniques = {"monkeypatch"} -> pytest
        self.repo_context_mock.detected_test_framework = None
        self.contract_mock.required_testing_techniques = ["monkeypatch"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        self.assertEqual(plan.test_framework, "pytest")
        self.assertTrue(plan.run_tests)

    def test_25_repo_none_required_unittest_mock_patch_resolves_unittest_greenfield(self):
        # 10. repo_framework = None, required_testing_techniques = {"unittest.mock.patch"} -> greenfield fallback to unittest
        self.repo_context_mock.detected_test_framework = None
        self.contract_mock.required_testing_techniques = ["unittest.mock.patch"]
        
        plan = _derive_gate_plan(self.repo_context_mock, self.contract_mock)
        self.assertEqual(plan.test_framework, "unittest")
        self.assertTrue(plan.run_tests)

    def test_26_validate_testing_policy_compatibility(self):
        from orchestrator import validate_testing_policy_compatibility, AcceptanceContract
        contract = AcceptanceContract(
            title="Test",
            description="Test",
            file_contracts=[],
            required_tests={},
            protected_tests={},
            forbidden_test_names=[],
            preserved_signatures={},
            preserved_behaviors=[],
            required_exports={},
            required_imports={},
            forbidden_imports={},
            required_patterns={},
            required_calls={},
            required_structures={},
            required_decorators={},
            required_testing_techniques=["monkeypatch"],
            forbidden_testing_techniques=[],
            forbidden_constructs={},
            relevant_context_files=[],
            forbidden_quality_tools=[],
            required_quality_tools=[]
        )
        
        errors = validate_testing_policy_compatibility("unittest", contract)
        self.assertEqual(len(errors), 1)
        self.assertIn("incompatible", errors[0])
        
        errors2 = validate_testing_policy_compatibility("none", contract)
        self.assertEqual(len(errors2), 1)
        self.assertIn("resuelto", errors2[0])
        
if __name__ == '__main__':
    unittest.main()
