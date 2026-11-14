class DomainError(Exception):
    """Base exception for domain layer."""
    pass


class ProviderNotInstalledError(DomainError):
    """Raised when a CLI binary is not installed on the system."""
    pass


class ProviderExecutionError(DomainError):
    """Raised when an error occurs during CLI or project provider execution."""
    pass


class BoardError(DomainError):
    """Raised when interacting with an external project board fails."""
    pass


class EntityNotFoundError(DomainError):
    """Raised when a queried entity is not found in the repository."""
    pass


class ValidationError(DomainError):
    """Raised when domain validation fails."""
    pass


class ContractViolationError(DomainError):
    """Raised when a provider does not fulfill the contract (port) it must implement."""
    pass
