import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
import hashlib

from orchestrator_core.repository_context import RepositoryContextManager, RepositoryIndexCache, PythonFileSummary
from orchestrator_core.schemas import ContextBudget, AcceptanceContract, RepositoryContext
from orchestrator_core.prompt_budget import PreflightError, PromptBudget, build_budget_safe_authoritative_evidence
from orchestrator_core.semantic_validators import validate_semantic_fidelity, SemanticFidelityError
from orchestrator_core.planning_agents import agent_generate_acceptance_contract
from orchestrator_core.runtime import RuntimeClients

def write_file(path: str, content: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# a. ranking
def test_ranking_deterministic_coverage(tmp_path):
    doc_a = tmp_path / "doc_a.md"
    doc_b = tmp_path / "doc_b.md"
    # doc_a has 20 REQ-A
    write_file(str(doc_a), "REQ-A\n" * 20)
    # doc_b has REQ-A, REQ-B, REQ-C
    write_file(str(doc_b), "REQ-A\nREQ-B\nREQ-C\n")

    issue = "Source Requirements: REQ-A, REQ-B, REQ-C"
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())

    keys = list(ctx.authoritative_context_files.keys())
    assert "doc_b.md" in keys
    assert "doc_a.md" not in keys

# b. first AcceptanceContract prompt
def test_first_acceptance_contract_prompt_marker(tmp_path):
    doc = tmp_path / "specs" / "doc.md"
    write_file(str(doc), "UNIQUE_AUTH_SOURCE_MARKER_123")
    issue = "Please follow specs/doc.md and implement."

    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    assert any("specs/doc.md" in k for k in ctx.authoritative_context_files)

    runtime = MagicMock()
    runtime.ai_client.models.generate_content.return_value = MagicMock(text='{"required_final_files": []}')

    try:
        agent_generate_acceptance_contract(
            title="title",
            description=issue,
            repository_context=ctx,
            runtime=runtime
        )
    except Exception as e:
        if "UNIQUE_AUTH_SOURCE_MARKER_123" not in str(e): # It might raise a Budget error but we mock it now
            pass

    # The FIRST call must have the block with UNIQUE_AUTH_SOURCE_MARKER_123
    if runtime.ai_client.models.generate_content.called:
        first_call_args = runtime.ai_client.models.generate_content.call_args[1]
        prompt = str(first_call_args.get('contents', ''))
        assert "UNIQUE_AUTH_SOURCE_MARKER_123" in prompt
    else:
        # If it failed before generation due to budget, we mock the budget
        with patch('orchestrator_core.prompt_budget.PromptBudget.can_add', return_value=True):
            try:
                agent_generate_acceptance_contract(
                    title="title",
                    description=issue,
                    repository_context=ctx,
                    runtime=runtime
                )
            except Exception:
                pass
        first_call_args = runtime.ai_client.models.generate_content.call_args[1]
        prompt = str(first_call_args.get('contents', ''))
        assert "UNIQUE_AUTH_SOURCE_MARKER_123" in prompt

# c. large-document Contract Generation
def test_large_document_contract_generation(tmp_path):
    doc = tmp_path / "large.md"
    content = "\n".join([f"Line {i}" for i in range(5000)])
    content += "\nREQ-HUGE is here.\n"
    content += "\n".join([f"Line {i}" for i in range(5000, 10000)])
    write_file(str(doc), content)

    issue = "Source Requirements: REQ-HUGE"
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())

    budget = PromptBudget(max_input_tokens=1000, reserved_output_tokens=0)
    auth_docs = ctx.authoritative_context_files
    resolved_refs = ctx.resolved_authoritative_references
    out = build_budget_safe_authoritative_evidence(auth_docs, issue, budget, "Test", resolved_refs)
    
    assert "REQ-HUGE" in out
    assert len(out) < len(content)

# d. Section normalization
def test_section_normalization(tmp_path):
    doc = tmp_path / "doc.md"
    write_file(str(doc), "# 4.1\nSomething important here.\n")
    
    issue = "Source Requirements: Sección 4.1"
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    
    # Excerpt generation
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0)
    out = build_budget_safe_authoritative_evidence(ctx.authoritative_context_files, issue, budget, "Test", ctx.resolved_authoritative_references)
    assert "4.1" in out

# e. multi-reference excerpt
def test_multi_reference_excerpt(tmp_path):
    doc = tmp_path / "doc.md"
    content = "REQ-A\n" + ("X\n" * 100) + "REQ-B\n" + ("Y\n" * 100) + "REQ-C\n"
    write_file(str(doc), content)
    
    issue = "Source Requirements: REQ-A, REQ-B, REQ-C"
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    
    budget = PromptBudget(max_input_tokens=500, reserved_output_tokens=0)
    out = build_budget_safe_authoritative_evidence(ctx.authoritative_context_files, issue, budget, "Test", ctx.resolved_authoritative_references)
    
    assert "REQ-A" in out
    assert "REQ-B" in out
    assert "REQ-C" in out

# f. missing required reference in excerpt
def test_missing_required_reference_in_excerpt():
    budget = PromptBudget(max_input_tokens=100, reserved_output_tokens=0)
    # The reference REQ-MISSING won't be found because it's not in the document.
    auth_docs = {"doc.md": "REQ-A\n" * 1000}
    with pytest.raises(PreflightError):
        build_budget_safe_authoritative_evidence(auth_docs, "REQ-A", budget, "Test", resolved_refs=["REQ-MISSING"])

# g. explicit missing path
def test_explicit_missing_path(tmp_path):
    doc = tmp_path / "other.md"
    # Mention it in text
    write_file(str(doc), "See docs/required_spec.md")
    
    issue = "Please follow docs/required_spec.md"
    manager = RepositoryContextManager(str(tmp_path))
    
    with pytest.raises(PreflightError) as exc:
        manager.build_repository_context(issue, ContextBudget())
    assert "no encontrado" in str(exc.value)

# h. neutral descriptive provenance
def test_neutral_descriptive_provenance(tmp_path):
    doc = tmp_path / "doc.md"
    # This lacks positive normative signal!
    write_file(str(doc), "CanonicalState currently includes external_id.")
    
    issue = "Source Requirements: doc.md"
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    
    contract = AcceptanceContract(
        required_structures={"foo.py": {"external_id": "field"}},
        protected_tests={},
        required_tests={},
        required_new_files=set(),
        required_modified_files=set(),
        required_final_files={"foo.py"}
    )
    
    with pytest.raises(SemanticFidelityError) as exc:
        validate_semantic_fidelity(contract, issue, "", ctx)
    assert "UNSUPPORTED_BINDING_OBLIGATION" in str(exc.value)

# i. positive normative signal
def test_positive_normative_provenance(tmp_path):
    doc = tmp_path / "doc.md"
    write_file(str(doc), "CanonicalState MUST include external_id.")
    
    issue = "Source Requirements: doc.md"
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    
    contract = AcceptanceContract(
        required_structures={"foo.py": {"external_id": "field"}},
        protected_tests={},
        required_tests={},
        required_new_files=set(),
        required_modified_files=set(),
        required_final_files={"foo.py"}
    )
    
    # Should not raise SemanticFidelityError
    validate_semantic_fidelity(contract, issue, "", ctx)

# j. negative normative signal
def test_negative_normative_provenance(tmp_path):
    doc = tmp_path / "doc.md"
    write_file(str(doc), "The implementation may use external_id as an optional example.")
    
    issue = "Source Requirements: doc.md"
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    
    contract = AcceptanceContract(
        required_structures={"foo.py": {"external_id": "field"}},
        protected_tests={},
        required_tests={},
        required_new_files=set(),
        required_modified_files=set(),
        required_final_files={"foo.py"}
    )
    
    with pytest.raises(SemanticFidelityError) as exc:
        validate_semantic_fidelity(contract, issue, "", ctx)
    assert "UNSUPPORTED_BINDING_OBLIGATION" in str(exc.value)

def test_markdown_source_requirements_parsing(tmp_path):
    issue = '**Source Requirements:** REQ-STATE-17, Sección 4.1, Business Rule Alpha'
    manager = RepositoryContextManager(str(tmp_path))
    refs = manager._discover_authoritative_references(issue)
    search_strs = [r[1] for r in refs]
    assert 'REQ-STATE-17' in search_strs
    assert '4.1' in search_strs
    assert 'Business Rule Alpha' in search_strs
    
    orig_strs = [r[0] for r in refs]
    assert 'REQ-STATE-17' in orig_strs
    assert 'Sección 4.1' in orig_strs

def test_section_style_reference_normalization(tmp_path):
    issue = 'Source Requirements: Section 5.2'
    manager = RepositoryContextManager(str(tmp_path))
    refs = manager._discover_authoritative_references(issue)
    assert refs[0][1] == '5.2'

def test_technical_resolver_failure_fail_closed(tmp_path):
    issue = 'Source Requirements: REQ-A'
    manager = RepositoryContextManager(str(tmp_path))
    with patch.object(manager, '_resolve_authoritative_documents', side_effect=OSError("Disk error")):
        with pytest.raises(PreflightError) as exc:
            manager.build_repository_context(issue, budget=ContextBudget())
        assert 'Technical error' in str(exc.value)

def test_unresolved_requirement_fail_closed(tmp_path):
    doc = tmp_path / "doc.md"
    write_file(str(doc), "REQ-A")
    issue = 'Source Requirements: REQ-A, REQ-MISSING'
    manager = RepositoryContextManager(str(tmp_path))
    with pytest.raises(PreflightError) as exc:
        manager.build_repository_context(issue, budget=ContextBudget())
    assert "REQ-MISSING" in str(exc.value)

def test_budget_full_document():
    budget = PromptBudget(max_input_tokens=1000, reserved_output_tokens=0)
    auth_docs = {'doc.md': 'REQ-A ' * 10}
    out = build_budget_safe_authoritative_evidence(auth_docs, 'REQ-A', budget, "Contexto", resolved_refs=['REQ-A'])
    assert 'REQ-A' in out

def test_budget_fail_closed():
    budget = PromptBudget(max_input_tokens=10, reserved_output_tokens=0)
    content = '\n'.join([f"Line {i}" for i in range(100)])
    content += '\nREQ-A occurs here\n'
    auth_docs = {'doc.md': content}
    with pytest.raises(PreflightError):
        build_budget_safe_authoritative_evidence(auth_docs, 'REQ-A', budget, "Contexto", resolved_refs=['REQ-A'])

def test_issue_provenance(tmp_path):
    # Binding issue provenance shouldn't require authoritative doc
    issue = 'Update the func1 to do something'
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    ctx.source_index = {"foo.py": PythonFileSummary(filepath="foo.py", functions=["func1"], classes=[], signatures={}, dependencies=[], is_test=False, module_name="foo", imports=[], exports=[], docstring_summary="", referenced_symbols=[], file_hash="hash", estimated_tokens=10)}
    contract = AcceptanceContract(
        required_calls={"foo.py": {"func1": []}},
        protected_tests={},
        required_tests={},
        required_new_files=set(),
        required_modified_files=set(),
        required_final_files={"foo.py"}
    )
    validate_semantic_fidelity(contract, issue, "", ctx)

def test_repo_provenance(tmp_path):
    # Physically verified repository provenance shouldn't require authoritative doc
    issue = 'Fix bug'
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    ctx.source_index = {"foo.py": PythonFileSummary(filepath="foo.py", functions=["caller", "callee"], classes=[], signatures={}, dependencies=[], is_test=False, module_name="foo", imports=[], exports=[], docstring_summary="", referenced_symbols=[], file_hash="hash", estimated_tokens=10)}
    
    import orchestrator_core.schemas
    req_call = orchestrator_core.schemas.RequiredCall(name="callee", is_async=False)
    contract = AcceptanceContract(
        required_calls={"foo.py": {"caller": [req_call]}},
        protected_tests={},
        required_tests={},
        required_new_files=set(),
        required_modified_files=set(),
        required_final_files={"foo.py"}
    )
    validate_semantic_fidelity(contract, issue, "", ctx)

def test_no_provenance(tmp_path):
    issue = 'Fix bug'
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    ctx.source_index = {"foo.py": PythonFileSummary(filepath="foo.py", functions=["caller"], classes=[], signatures={}, dependencies=[], is_test=False, module_name="foo", imports=[], exports=[], docstring_summary="", referenced_symbols=[], file_hash="hash", estimated_tokens=10)}
    
    import orchestrator_core.schemas
    req_call = orchestrator_core.schemas.RequiredCall(name="unknown_callee", is_async=False)
    contract = AcceptanceContract(
        required_calls={"foo.py": {"caller": [req_call]}},
        protected_tests={},
        required_tests={},
        required_new_files=set(),
        required_modified_files=set(),
        required_final_files={"foo.py"}
    )
    with pytest.raises(SemanticFidelityError):
        validate_semantic_fidelity(contract, issue, "", ctx)
        
def test_explicit_path_resolution(tmp_path):
    specs = tmp_path / 'specs' / 'domain_rules.md'
    write_file(str(specs), 'SPEC_CONTENT\nUNIQUE_AUTH_SOURCE_MARKER_7319\n')

    issue = 'Please follow specs/domain_rules.md and implement accordingly.'
    manager = RepositoryContextManager(str(tmp_path))
    budget = ContextBudget()
    ctx = manager.build_repository_context(issue, budget)

    keys = list(ctx.authoritative_context_files.keys())
    assert any('specs/domain_rules.md' in k for k in keys)

def test_validate_relevant_context_files(tmp_path):
    specs = tmp_path / 'specs' / 'domain_rules.md'
    write_file(str(specs), 'SPEC_CONTENT\nUNIQUE_AUTH_SOURCE_MARKER_7319\n')
    issue = 'Please follow specs/domain_rules.md and implement accordingly.'
    manager = RepositoryContextManager(str(tmp_path))
    ctx = manager.build_repository_context(issue, ContextBudget())
    from orchestrator_core.contract_validation import validate_relevant_context_files
    contract = AcceptanceContract(
        required_final_files={"foo.py"},
        required_new_files=set(),
        required_modified_files=set(),
        required_structures={},
        protected_tests={},
        required_tests={}
    )
    # The requirement is just "explicitly assert: validate_relevant_context_files(...) == []"
    assert validate_relevant_context_files(ctx, contract) == []