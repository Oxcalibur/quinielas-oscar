with open('tests/test_modularization_contract.py', 'r', encoding='utf-8') as f:
    content = f.read()

bad_replacement = '''        "validate_relevant_context_files", "canonicalize_testing_technique",
        "validate_contract_consistency", "_create_file_contract",
        "_check_forbidden_constructs", "_check_exports", "_check_tests",
        "_check_imports", "_check_patterns", "_check_calls", "_check_structures",
        "_get_decorator_name", "_check_decorators", "_check_preserved_signatures",
        "_check_testing_techniques", "validate_contractual_ast", "validate_design",
        "validate_generated_manifest", "validate_final_state": "def estimate_repository_context_tokens(repo_context: RepositoryContext, issue_description: str, contract: AcceptanceContract | None=None) -> int",'''

good_replacement = '        "estimate_repository_context_tokens": "def estimate_repository_context_tokens(repo_context: RepositoryContext, issue_description: str, contract: AcceptanceContract | None=None) -> int",'

content = content.replace(bad_replacement, good_replacement)

with open('tests/test_modularization_contract.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed!')
