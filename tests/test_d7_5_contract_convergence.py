import pytest
from unittest.mock import patch, MagicMock

from orchestrator_core.schemas import AcceptanceContract, RepositoryContext
from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError
from orchestrator import generate_validated_acceptance_contract

def test_b_out_of_scope_does_not_contaminate_other_sections():
    # Issue:
    # ## Out of Scope
    # Agent orchestration logic
    #
    # ## Acceptance Criteria
    # src/state.py is required.
    contract = AcceptanceContract(
        required_new_files={"src/state.py"}
    )
    desc = "## Out of Scope\nAgent orchestration logic\n\n## Acceptance Criteria\nsrc/state.py is required."
    validate_semantic_fidelity(contract, "Title", desc, RepositoryContext())

def test_c_real_interaction_out_of_scope_and_estimated_files():
    # Issue:
    # **Out of Scope:** Agent orchestration logic.
    # **Estimated Files (NON-BINDING HINT):** `src/state.py`
    contract = AcceptanceContract(
        required_new_files={"src/state.py"}
    )
    desc = "**Out of Scope:** Agent orchestration logic.\n\n**Estimated Files (NON-BINDING HINT):** `src/state.py`"

    with pytest.raises(SemanticFidelityError) as exc_info:
        validate_semantic_fidelity(contract, "Title", desc, RepositoryContext())

    assert "has only non-binding provenance" in str(exc_info.value)
    assert "conflicts with explicit out-of-scope constraint" not in str(exc_info.value)

def test_d_binding_and_out_of_scope_same_term():
    # Issue:
    # ## Acceptance Criteria
    # src/state.py is required.
    #
    # ## Out of Scope
    # Modifying src/state.py
    contract = AcceptanceContract(
        required_new_files={"src/state.py"}
    )
    desc = "## Acceptance Criteria\nsrc/state.py is required.\n\n## Out of Scope\nModifying src/state.py"

    with pytest.raises(SemanticFidelityError) as exc_info:
        validate_semantic_fidelity(contract, "Title", desc, RepositoryContext())

    assert "conflicts with explicit out-of-scope constraint" in str(exc_info.value)

def test_e_multiple_semantic_violations_in_one_attempt():
    # Issue:
    # ## Estimated Files
    # a.py
    # b.py
    #
    # ## Recommendations
    # Use zeta
    # Use alpha
    contract = AcceptanceContract(
        required_new_files={"b.py", "a.py"},
        required_imports={"src/foo.py": ["from zeta import Model", "import alpha"]}
    )
    desc = "## Estimated Files\na.py\nb.py\n\n## Recommendations\nUse zeta\nUse alpha"

    with pytest.raises(SemanticFidelityError) as exc_info:
        validate_semantic_fidelity(contract, "Title", desc, RepositoryContext())

    err_str = str(exc_info.value)
    # verify a.py < b.py
    assert err_str.index("a.py") < err_str.index("b.py")

    # "from zeta import Model" is lexically BEFORE "import alpha"
    # But normalized: "zeta" vs "alpha", so "alpha" should appear BEFORE "zeta"
    assert err_str.index("alpha") < err_str.index("zeta")

@patch('orchestrator.agent_generate_acceptance_contract')
@patch('orchestrator._derive_gate_plan')
@patch('orchestrator.tool_preflight', return_value=[])
@patch('orchestrator.validate_contract_capabilities', return_value=(True, []))
@patch('orchestrator.validate_relevant_context_files', return_value=[])
@patch('orchestrator.validate_testing_policy_compatibility', return_value=[])
def test_g_cumulative_retry_memory(mock_vtpc, mock_vrcf, mock_vcc, mock_tp, mock_dgp, mock_agent):
    from orchestrator_core.exceptions import SemanticFidelityError, ContractCapabilityError

    # Attempt 1 -> SemanticFidelityError("A")
    # Attempt 2 -> ContractCapabilityError("B")
    # Attempt 3 -> success

    valid_contract = AcceptanceContract(required_new_files={"a.py"})

    def side_effect(*args, **kwargs):
        prior_feedback = kwargs.get('prior_feedback', '')

        # Track the feedback received on each call
        side_effect.feedback_history.append(prior_feedback)

        if side_effect.call_count == 1:
            side_effect.call_count += 1
            raise SemanticFidelityError("Violation A")
        elif side_effect.call_count == 2:
            side_effect.call_count += 1
            # Return valid contract for capability error to occur (must pass semantic fidelity)
            return valid_contract
        else:
            side_effect.call_count += 1
            return valid_contract

    side_effect.call_count = 1
    side_effect.feedback_history = []

    mock_agent.side_effect = side_effect

    # Mock gate plan to avoid PreflightError
    mock_gate_plan = MagicMock()
    mock_gate_plan.test_framework = "pytest"
    mock_dgp.return_value = mock_gate_plan

    # We need capability validation to fail on second attempt
    def capability_side_effect(*args, **kwargs):
        if capability_side_effect.call_count == 1:
            capability_side_effect.call_count += 1
            return False, ["Violation B"]
        return True, []

    capability_side_effect.call_count = 1
    mock_vcc.side_effect = capability_side_effect

    mock_runtime = MagicMock()
    mock_context_budget = MagicMock()
    mock_context_budget.maximum_input_tokens = 100000
    mock_context_budget.reserved_output_tokens = 4096
    mock_context_manager = MagicMock()

    # Function should complete successfully without exceptions
    generate_validated_acceptance_contract("Title", "Desc", RepositoryContext(), mock_runtime, mock_context_budget, mock_context_manager)

    assert len(side_effect.feedback_history) == 3

    # Attempt 1 feedback empty
    assert side_effect.feedback_history[0] == ""

    # Attempt 2 feedback contains A
    assert "Violation A" in side_effect.feedback_history[1]
    assert "Violation B" not in side_effect.feedback_history[1]

    # Attempt 3 feedback contains A and B
    assert "Violation A" in side_effect.feedback_history[2]
    assert "Violation B" in side_effect.feedback_history[2]

    assert side_effect.call_count == 4  # Because it was initialized to 1 and incremented 3 times
    assert mock_agent.call_count == 3

@patch('orchestrator.agent_generate_acceptance_contract')
@patch('orchestrator._derive_gate_plan')
@patch('orchestrator.tool_preflight', return_value=[])
@patch('orchestrator.validate_contract_capabilities', return_value=(True, []))
@patch('orchestrator.validate_relevant_context_files', return_value=[])
def test_h_deduplication_of_cumulative_feedback(mock_vrcf, mock_vcc, mock_tp, mock_dgp, mock_agent):
    from orchestrator_core.exceptions import SemanticFidelityError

    valid_contract = AcceptanceContract(required_new_files={"a.py"})

    def side_effect(*args, **kwargs):
        prior_feedback = kwargs.get('prior_feedback', '')
        side_effect.feedback_history.append(prior_feedback)

        if side_effect.call_count == 1:
            side_effect.call_count += 1
            raise SemanticFidelityError("Violation A")
        elif side_effect.call_count == 2:
            side_effect.call_count += 1
            raise SemanticFidelityError("Violation A")
        else:
            return valid_contract

    side_effect.call_count = 1
    side_effect.feedback_history = []

    mock_agent.side_effect = side_effect
    mock_dgp.return_value = MagicMock()
    mock_vcc.return_value = (True, [])
    mock_runtime = MagicMock()
    mock_context_budget = MagicMock()
    mock_context_budget.maximum_input_tokens = 100000
    mock_context_budget.reserved_output_tokens = 10000
    mock_context_manager = MagicMock()

    generate_validated_acceptance_contract("Title", "Desc", RepositoryContext(), mock_runtime, mock_context_budget, mock_context_manager)

    assert len(side_effect.feedback_history) == 3
    assert side_effect.feedback_history[0] == ""
    assert side_effect.feedback_history[1].count("Violation A") == 1
    assert side_effect.feedback_history[2].count("Violation A") == 1
    assert mock_agent.call_count == 3

@patch('orchestrator.agent_generate_acceptance_contract')
def test_i_maximum_attempts_unchanged(mock_agent):
    from orchestrator_core.exceptions import SemanticFidelityError, ContractGenerationExhaustedError

    mock_agent.side_effect = SemanticFidelityError("persistent violation")
    mock_runtime = MagicMock()
    mock_context_budget = MagicMock()
    mock_context_budget.maximum_input_tokens = 100000
    mock_context_budget.reserved_output_tokens = 10000
    mock_context_manager = MagicMock()

    with pytest.raises(ContractGenerationExhaustedError) as exc_info:
        generate_validated_acceptance_contract("Title", "Desc", RepositoryContext(), mock_runtime, mock_context_budget, mock_context_manager)

    assert mock_agent.call_count == 3
    assert len(exc_info.value.diagnostics) == 3
