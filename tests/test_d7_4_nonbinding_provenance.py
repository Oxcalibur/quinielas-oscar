import pytest
from orchestrator_core.schemas import AcceptanceContract, RepositoryContext
from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError

def test_a_recommended_wording_normalized_import():
    # Issue: "Pydantic v2 is recommended"
    # Contrato: required_imports = {"src/schema.py": ["from pydantic import BaseModel"]}
    # Sin otra provenance.
    # Esperado: nonbinding_escalation
    contract = AcceptanceContract(
        required_imports={"src/schema.py": ["from pydantic import BaseModel"]}
    )
    repo_context = RepositoryContext()

    with pytest.raises(SemanticFidelityError) as exc_info:
        validate_semantic_fidelity(contract, "Title", "Pydantic v2 is recommended", repo_context)

    assert "nonbinding_escalation" in str(exc_info.value)
    assert "pydantic" in str(exc_info.value).lower()

def test_b_binding_issue_occurrence_overrides_nonbinding_duplicate():
    # Issue:
    # ## Acceptance Criteria
    # src/state.py is required for state handling.
    #
    # ## Estimated Files
    # src/state.py
    # Contrato requiere src/state.py. Esperado: ACCEPT.
    contract = AcceptanceContract(
        required_new_files={"src/state.py"}
    )
    repo_context = RepositoryContext()

    desc = "## Acceptance Criteria\nsrc/state.py is required for state handling.\n\n## Estimated Files\nsrc/state.py"

    # Debe pasar sin excepción
    validate_semantic_fidelity(contract, "Title", desc, repo_context)

def test_c_binding_authoritative_provenance_overrides_nonbinding_issue_hint():
    # Issue:
    # ## Estimated Files
    # src/state.py
    # Authoritative context:
    # src/state.py is required for state persistence.
    # Contrato requiere src/state.py. Esperado: ACCEPT.
    contract = AcceptanceContract(
        required_new_files={"src/state.py"}
    )
    repo_context = RepositoryContext(
        authoritative_context_files={"doc.md": "src/state.py is required for state persistence."}
    )

    desc = "## Estimated Files\nsrc/state.py"

    validate_semantic_fidelity(contract, "Title", desc, repo_context)

def test_d_recommended_import_plus_independent_authoritative_binding_provenance():
    # Issue:
    # ## Recommendations
    # Use library_x.
    # Authoritative source:
    # library_x is required for serialization.
    # Contrato requiere: from library_x import Model
    # Esperado: ACCEPT.
    contract = AcceptanceContract(
        required_imports={"src/schema.py": ["from library_x import Model"]}
    )
    repo_context = RepositoryContext(
        authoritative_context_files={"doc.md": "library_x is required for serialization."}
    )

    desc = "## Recommendations\nUse library_x."

    validate_semantic_fidelity(contract, "Title", desc, repo_context)

def test_f_optional_pattern_plus_independent_binding_provenance():
    # Issue contiene el patrón solo como optional choice.
    # Authoritative source lo declara explícitamente obligatorio.
    # Esperado: ACCEPT.
    contract = AcceptanceContract(
        required_patterns={"src/service.py": ["log_before_raise"]}
    )
    repo_context = RepositoryContext(
        authoritative_context_files={"doc.md": "log_before_raise is required."}
    )

    desc = "## Optional choices\nYou can use log_before_raise."

    validate_semantic_fidelity(contract, "Title", desc, repo_context)
