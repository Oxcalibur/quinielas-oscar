class ContractGenerationError(Exception):
    pass

class PreflightError(Exception):
    pass

class CandidateSchemaError(ContractGenerationError):
    pass

class SemanticFidelityError(ContractGenerationError):
    pass

class ContractConsistencyError(ContractGenerationError):
    pass

class ContractPreflightError(PreflightError):
    pass

class EnvironmentPreflightError(PreflightError):
    pass

class ContractCapabilityError(ContractGenerationError):
    pass

class ContractGenerationExhaustedError(ContractGenerationError):
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or []

class InfrastructureGenerationError(ContractGenerationError):
    pass
