"""Expected repository outcomes safe to translate at the HTTP boundary.

Only raise these with fixed, content-free codes. Validation of stored data and
programming errors must propagate to the sanitized internal-error handler.
"""


class ResourceNotFoundError(LookupError):
    """The requested resource does not exist."""


class ResourceConflictError(ValueError):
    """The requested action conflicts with the current resource state."""
