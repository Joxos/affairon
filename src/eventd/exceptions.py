"""Exception hierarchy for eventd.

All custom exceptions inherit from EventdError base class.
"""


class EventdError(Exception):
    """Base exception for all eventd errors.

    All custom exceptions in the eventd framework inherit from this class,
    allowing users to catch all framework-specific errors with a single except clause.
    """


class EventValidationError(EventdError, ValueError):
    """Event validation failed.

    Raised when:
    - User-provided event fields fail pydantic validation
    - Reserved fields (event_id, timestamp) are provided during construction

    This wraps pydantic.ValidationError to provide a framework-specific exception type.
    """


class CyclicDependencyError(EventdError, ValueError):
    """Cyclic dependency detected in listener after chain.

    Raised when:
    - Registering a listener with 'after' dependencies that form a cycle
    - resolve_order() detects a cycle during topological sort (defensive check)

    This wraps graphlib.CycleError when using TopologicalSorter.
    """


class KeyConflictError(EventdError, ValueError):
    """Key conflict when merging listener return values.

    Raised when multiple listeners return dictionaries with overlapping keys.
    Users must ensure listener return values have unique keys, or handle
    conflicts by restructuring their return values.
    """
