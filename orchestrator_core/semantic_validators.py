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

    authoritative_docs = list(getattr(repo_context, 'authoritative_context_files', {}).values())

    def check_issue_provenance(term: str, title: str, desc: str) -> tuple[bool, bool, bool, bool]:
        term_lower = term.lower()
        is_present = False
        has_binding = False
        has_nonbinding = False
        has_out_of_scope = False

        if term_lower in title.lower():
            is_present = True
            has_binding = True

        non_binding_markers = [
            "estimated files",
            "recommendation", "recommendations", "recommended",
            "recomendación", "recomendaciones", "recomendado",
            "optional", "optional choices", "optional choice",
            "suggestion", "suggested",
            "sugerencia", "sugerido",
            "example", "examples",
            "ejemplo", "ejemplos",
            "non-binding",
            "implementation open choice"
        ]
        out_of_scope_markers = [
            "out of scope",
            "out-of-scope",
            "fuera de alcance"
        ]

        in_non_binding_section = False
        in_out_of_scope_section = False

        for line in desc.splitlines():
            line_lower = line.lower()
            heading_match = re.match(r'^(#{1,6})\s+(.*)', line_lower)
            if heading_match:
                heading_text = heading_match.group(2)
                in_non_binding_section = any(marker in heading_text for marker in non_binding_markers)
                in_out_of_scope_section = any(marker in heading_text for marker in out_of_scope_markers)

            if term_lower in line_lower:
                is_present = True
                has_inline_non_binding = any(marker in line_lower for marker in non_binding_markers)
                has_inline_out_of_scope = any(marker in line_lower for marker in out_of_scope_markers)

                is_oos = in_out_of_scope_section or has_inline_out_of_scope
                is_nb = in_non_binding_section or has_inline_non_binding

                if is_oos:
                    has_out_of_scope = True
                if is_nb and not is_oos:
                    has_nonbinding = True
                if not is_oos and not is_nb:
                    has_binding = True

        return is_present, has_binding, has_nonbinding, has_out_of_scope

    def normalize_import_for_provenance(import_str: str) -> str:
        import_str = import_str.strip()
        match = re.match(r'^from\s+([a-zA-Z0-9_\.]+)\s+import', import_str)
        if match:
            return match.group(1).split('.')[0]
        match = re.match(r'^import\s+([a-zA-Z0-9_\.]+)', import_str)
        if match:
            return match.group(1).split('.')[0]
        return import_str.split('.')[0]

    def has_binding_authoritative_provenance(term: str, authoritative_docs: list[str]) -> bool:
        if not authoritative_docs:
            return False

        term_lower = term.lower()
        non_binding_markers = [
            "example", "ejemplo",
            "recommendation", "recomendación", "recomendacion", "recommended", "recomendado",
            "optional", "opcional",
            "suggested", "suggestion", "sugerido", "sugerencia",
            "may", "non-binding", "estimated", "implementation open choice"
        ]
        positive_markers = [
            "must", "shall", "required", "requires", "mandatory",
            "debe", "deberá", "obligatorio", "requerido"
        ]

        for doc in authoritative_docs:
            for line in doc.splitlines():
                line_lower = line.lower()
                if term_lower in line_lower:
                    has_non_binding = any(marker in line_lower for marker in non_binding_markers)
                    has_positive = any(marker in line_lower for marker in positive_markers)
                    if not has_non_binding and has_positive:
                        return True
        return False

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

    fidelity_errors = []

    # Out of scope conflicts and Nonbinding escalation
    for filename in sorted(contract.required_final_files | contract.required_modified_files | contract.required_new_files):
        is_present, has_binding, has_nonbinding, has_out_of_scope = check_issue_provenance(filename, title, desc)
        if has_out_of_scope:
            fidelity_errors.append(f"nonbinding_escalation: required file '{filename}' conflicts with explicit out-of-scope constraint")
        elif is_present and not has_binding:
            if not has_binding_authoritative_provenance(filename, authoritative_docs):
                fidelity_errors.append(f"nonbinding_escalation: required file '{filename}' has only non-binding provenance")

    for filepath in sorted(contract.required_imports):
        deps = sorted(
            contract.required_imports[filepath],
            key=lambda dep: (
                normalize_import_for_provenance(dep),
                dep
            )
        )
        for dep in deps:
            normalized_dep = normalize_import_for_provenance(dep)
            is_present, has_binding, has_nonbinding, has_out_of_scope = check_issue_provenance(normalized_dep, title, desc)
            if has_out_of_scope:
                fidelity_errors.append(f"nonbinding_escalation: required_imports '{normalized_dep}' conflicts with explicit out-of-scope constraint")
            elif is_present and not has_binding:
                if not has_binding_authoritative_provenance(normalized_dep, authoritative_docs):
                    fidelity_errors.append(f"nonbinding_escalation: required_imports '{normalized_dep}' has only non-binding provenance")

    for filepath in sorted(contract.required_patterns.keys()):
        patterns = contract.required_patterns[filepath]
        for pattern in sorted(patterns):
            is_present, has_binding, has_nonbinding, has_out_of_scope = check_issue_provenance(pattern, title, desc)
            if has_out_of_scope:
                fidelity_errors.append(f"nonbinding_escalation: required_patterns '{pattern}' conflicts with explicit out-of-scope constraint")
            elif is_present and not has_binding:
                if not has_binding_authoritative_provenance(pattern, authoritative_docs):
                    fidelity_errors.append(f"nonbinding_escalation: required_patterns '{pattern}' has only non-binding provenance")
            elif not is_present:
                if not has_binding_authoritative_provenance(pattern, authoritative_docs):
                    fidelity_errors.append(f"UNSUPPORTED_BINDING_OBLIGATION: {pattern}")

    if fidelity_errors:
        unique_errors = []
        for err in fidelity_errors:
            if err not in unique_errors:
                unique_errors.append(err)
        raise SemanticFidelityError("\n".join(unique_errors))

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
                    if not has_binding_authoritative_provenance(callee_name, authoritative_docs) and not has_binding_authoritative_provenance(caller_func, authoritative_docs):
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
                if not has_binding_authoritative_provenance(var_name, authoritative_docs):
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
            if not has_binding_authoritative_provenance(tool, authoritative_docs):
                raise SemanticFidelityError(
                    f"UNSUPPORTED_BINDING_OBLIGATION: required_quality_tools '{tool}' "
                    "has neither binding Issue provenance nor verified repository evidence."
                )
