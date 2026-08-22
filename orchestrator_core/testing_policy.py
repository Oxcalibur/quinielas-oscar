from typing import Literal
from orchestrator_core.schemas import FileContract, RepositoryContext
from orchestrator_core.contract_validation import canonicalize_testing_technique

def resolve_mocking_instruction(framework: Literal["pytest", "unittest"], file_contract: FileContract, repo_context: RepositoryContext) -> str:
    forbidden = {
        canonicalize_testing_technique(t)
        for t in file_contract.forbidden_testing_techniques
    }
    required = {
        canonicalize_testing_technique(t)
        for t in file_contract.required_testing_techniques
    }
    
    if framework == "unittest":
        if "unittest.mock.patch" in forbidden:
            return "Usa las utilidades estándar de unittest permitidas por el contrato sin aplicar técnicas prohibidas."
        return "Usa unittest.mock.patch para aislar dependencias."
    
    if required:
        if "pytest-mock" in required:
            return "Usa pytest-mock mediante el fixture mocker."
        if "monkeypatch" in required:
            return "Usa el fixture monkeypatch."
        if "unittest.mock.patch" in required:
            return "Usa unittest.mock.patch dentro de la suite pytest."
    
    candidates = []
    if "pytest-mock" not in forbidden:
        candidates.append("pytest-mock mediante el fixture mocker")
    
    if "monkeypatch" not in forbidden:
        candidates.append("el fixture monkeypatch")
        
    if candidates:
        return f"Usa {' o '.join(candidates)} para aislar dependencias."
        
    return (
        "Usa pytest respetando el contrato, sin pytest-mock, "
        "mocker ni monkeypatch."
    )

