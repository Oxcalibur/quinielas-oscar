import re
from orchestrator_core.schemas import AcceptanceContract, RepositoryContext
from orchestrator_core.exceptions import SemanticFidelityError

def validate_semantic_fidelity(contract: AcceptanceContract, title: str, desc: str, repo_context: RepositoryContext) -> None:
    """
    Validates that the generated AcceptanceContract maintains semantic fidelity
    with the intent of the original issue.
    """
    title_desc_lower = f"{title} {desc}".lower()
    mentions_tests = "test" in title_desc_lower

    # Check if there are testing requirements
    has_test_files = False
    for filename in contract.required_final_files | contract.required_new_files | contract.required_modified_files:
        if filename in repo_context.source_index and repo_context.source_index[filename].is_test:
            has_test_files = True
            break
        if "test" in filename.lower():
            has_test_files = True
            break

    has_protected = bool(contract.protected_tests)
    has_required = bool(contract.required_tests)

    if mentions_tests and not (has_test_files or has_protected or has_required):
        if "no new tests" not in title_desc_lower and "tests are optional" not in title_desc_lower and "tests optional" not in title_desc_lower:
            raise SemanticFidelityError("missing_binding_test_obligation")

    # Out of scope files
    for filename in contract.required_final_files | contract.required_modified_files | contract.required_new_files:
        if filename.lower() in title_desc_lower and "out of scope" in title_desc_lower:
            raise SemanticFidelityError(f"nonbinding_escalation: {filename}")

    # Estimated Files / Recommendations / Optional choices
    # Nonbinding escalation
    # If the file is in estimated files, it shouldn't be in required
    for filename in contract.required_final_files | contract.required_modified_files | contract.required_new_files:
        if "estimated files" in title_desc_lower and filename.lower() in title_desc_lower:
            raise SemanticFidelityError(f"nonbinding_escalation: {filename}")

    for deps in contract.required_imports.values():
        for dep in deps:
            if "recommendation" in title_desc_lower and dep.lower() in title_desc_lower:
                raise SemanticFidelityError(f"nonbinding_escalation: {dep}")

    for patterns in contract.required_patterns.values():
        for pattern in patterns:
            if "optional choice" in title_desc_lower and pattern.lower() in title_desc_lower:
                raise SemanticFidelityError(f"nonbinding_escalation: {pattern}")
            if pattern.lower() not in title_desc_lower:
                raise SemanticFidelityError(f"UNSUPPORTED_BINDING_OBLIGATION: {pattern}")

    # --- required_calls provenance enforcement ---
    # For each mandatory call obligation, either:
    #   (a) binding Issue provenance: the callee name appears in the issue text, OR
    #   (b) physically verified repo provenance: the caller AND callee are both found
    #       in the repo source_index signatures/functions for the specified file.
    all_source_functions: set[str] = set()
    for summary in repo_context.source_index.values():
        all_source_functions.update(summary.functions)
        all_source_functions.update(summary.signatures.keys())

    for filepath, caller_map in contract.required_calls.items():
        for caller_func, required_calls_list in caller_map.items():
            for req_call in required_calls_list:
                callee_name = req_call.name
                # Check binding Issue provenance
                has_issue_provenance = callee_name.lower() in title_desc_lower or caller_func.lower() in title_desc_lower
                # Check physically verified repository provenance:
                # Both caller and callee must appear in the actual source index for that file
                file_summary = repo_context.source_index.get(filepath)
                if file_summary is not None:
                    caller_in_repo = caller_func in file_summary.functions or caller_func in file_summary.signatures
                    callee_in_repo = callee_name in all_source_functions
                    has_repo_provenance = caller_in_repo and callee_in_repo
                else:
                    has_repo_provenance = False
                if not has_issue_provenance and not has_repo_provenance:
                    raise SemanticFidelityError(
                        f"UNSUPPORTED_BINDING_OBLIGATION: required_calls {caller_func}->{callee_name} in {filepath} "
                        "has neither binding Issue provenance nor verified repository evidence."
                    )

    # --- required_structures provenance enforcement ---
    # For each mandatory structure obligation, either:
    #   (a) binding Issue provenance: the var_name appears in the issue text, OR
    #   (b) physically verified repo provenance: the var_name is found in the
    #       repo source_index for the specified file.
    for filepath, struct_map in contract.required_structures.items():
        for var_name, check_type in struct_map.items():
            has_issue_provenance = var_name.lower() in title_desc_lower
            file_summary = repo_context.source_index.get(filepath)
            # Repository evidence: var_name appears in the file's known functions or signatures
            if file_summary is not None:
                has_repo_provenance = (
                    var_name in file_summary.functions or
                    var_name in file_summary.signatures
                )
            else:
                has_repo_provenance = False
            if not has_issue_provenance and not has_repo_provenance:
                raise SemanticFidelityError(
                    f"UNSUPPORTED_BINDING_OBLIGATION: required_structures {var_name} ({check_type}) in {filepath} "
                    "has neither binding Issue provenance nor verified repository evidence."
                )

    # --- required_quality_tools provenance enforcement ---
    # For each mandatory quality tool obligation, either:
    #   (a) binding Issue provenance: the tool name appears in the issue text, OR
    #   (b) verified repo provenance: the tool appears in detected_quality_tools
    #       (from structured_config.detected_quality_tools or repo_context.detected_quality_tools).
    detected_tools_lower: set[str] = set()
    if hasattr(repo_context, 'detected_quality_tools') and repo_context.detected_quality_tools:
        detected_tools_lower.update(t.lower() for t in repo_context.detected_quality_tools)
    if hasattr(repo_context, 'structured_config') and hasattr(repo_context.structured_config, 'detected_quality_tools'):
        detected_tools_lower.update(t.lower() for t in repo_context.structured_config.detected_quality_tools)

    for tool in contract.required_quality_tools:
        has_issue_provenance = tool.lower() in title_desc_lower
        has_repo_provenance = tool.lower() in detected_tools_lower
        if not has_issue_provenance and not has_repo_provenance:
            raise SemanticFidelityError(
                f"UNSUPPORTED_BINDING_OBLIGATION: required_quality_tools '{tool}' "
                "has neither binding Issue provenance nor verified repository evidence."
            )
