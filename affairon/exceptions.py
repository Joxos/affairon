"""Exception hierarchy for affairon.

All custom exceptions inherit from AffairdError base class.
"""


class AffairdError(Exception):
    """Base exception for all affairon errors.

    All custom exceptions in the affairon framework inherit from this class,
    allowing users to catch all framework-specific errors with a single except clause.
    """


class AffairValidationError(AffairdError, ValueError):
    """Affair validation failed.

    Raised when:
    - User-provided affair fields fail pydantic validation
    - Reserved fields (affair_id, timestamp) are provided during construction

    This wraps pydantic.ValidationError to provide a framework-specific exception type.
    """


class CyclicDependencyError(AffairdError, ValueError):
    """Cyclic dependency detected in listener after chain.

    Raised when:
    - Registering a listener with 'after' dependencies that form a cycle
    - resolve_order() detects a cycle during topological sort (defensive check)

    This wraps graphlib.CycleError when using TopologicalSorter.
    """


class KeyConflictError(AffairdError, ValueError):
    """Key conflict when merging listener return values.

    Raised when multiple listeners return dictionaries with overlapping keys.
    Users must ensure listener return values have unique keys, or handle
    conflicts by restructuring their return values.
    """
