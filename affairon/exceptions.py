"""Exception hierarchy for affairon.

All custom exceptions inherit from AffairError base class.
"""


class AffairError(Exception):
    """Base exception for all affairon errors.

    All custom exceptions in the affairon framework inherit from this class,
    allowing users to catch all framework-specific errors with a single except clause.
    """


class AffairValidationError(AffairError, ValueError):
    """Affair validation failed.

    Raised when user-provided affair fields fail pydantic validation.

    This wraps pydantic.ValidationError to provide a framework-specific exception type.
    """


class CyclicDependencyError(AffairError, ValueError):
    """Cyclic dependency detected in listener after chain.

    Raised when:
    - Registering a listener with 'after' dependencies that form a cycle
    - resolve_order() detects a cycle during topological sort (defensive check)

    This wraps graphlib.CycleError when using TopologicalSorter.
    """


class KeyConflictError(AffairError, ValueError):
    """Key conflict when merging listener return values.

    Raised when multiple listeners return dictionaries with overlapping keys.
    Users must ensure listener return values have unique keys, or handle
    conflicts by restructuring their return values.
    """


# -- Plugin errors ------------------------------------------------------------


class PluginError(AffairError):
    """Base exception for plugin loading errors."""


class PluginNotFoundError(PluginError):
    """Required plugin package is not installed.

    Raised when a plugin declared in [tool.affairon] plugins list
    cannot be found among installed packages.
    """


class PluginVersionError(PluginError):
    """Installed plugin version does not satisfy the requirement specifier.

    Raised when a plugin is installed but its version does not match
    the version constraint declared by the host application.
    """


class PluginEntryPointError(PluginError):
    """Plugin has no entry point in the 'affairon' group.

    Raised when a plugin package is installed but does not declare
    an entry point in the 'affairon' entry point group.
    """


class PluginImportError(PluginError):
    """Plugin module failed to import.

    Raised when a plugin's entry point module or a local plugin module
    raises an exception during import. The original exception is chained
    via ``__cause__``.
    """
