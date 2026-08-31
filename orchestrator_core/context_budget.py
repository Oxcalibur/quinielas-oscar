from orchestrator_core.schemas import AcceptanceContract, RepositoryContext

def estimate_repository_context_tokens(repo_context: RepositoryContext, issue_description: str, contract: AcceptanceContract | None = None) -> int:
    toks = 2000 # fixed overhead
    toks += len(issue_description) // 4
    if contract:
        toks += len(contract.model_dump_json()) // 4
    
    if repo_context.architecture_document:
        toks += len(repo_context.architecture_document) // 4
    
    toks += sum(len(c) // 4 for c in repo_context.project_configuration.values())
    
    if hasattr(repo_context, 'structured_config') and repo_context.structured_config:
        toks += len(repo_context.structured_config.model_dump_json()) // 4
        
    if hasattr(repo_context, 'quality_policy') and repo_context.quality_policy:
        toks += len(repo_context.quality_policy.model_dump_json()) // 4
    
    for c in repo_context.relevant_source_files.values(): toks += len(c) // 4
    for c in repo_context.relevant_test_files.values(): toks += len(c) // 4
    for c in getattr(repo_context, 'authoritative_context_files', {}).values(): toks += len(c) // 4
    for c in repo_context.dependency_files.values(): toks += len(c) // 4
    if repo_context.repository_map:
        toks += len(repo_context.repository_map) // 4
        
    return toks
