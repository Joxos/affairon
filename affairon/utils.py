from typing import Any

from affairon.exceptions import KeyConflictError


def callable_name(cb: Any) -> str:
    """Return a human-readable name for a callable, safe for logging.

    Falls back through ``__qualname__``, ``__name__``, and ``repr()``
    so that ``functools.partial``, callable instances, and other exotic
    callables never raise ``AttributeError``.

    Args:
        cb: Any callable object.

    Returns:
        Display name string.
    """
    return (
        getattr(cb, "__qualname__", None) or getattr(cb, "__name__", None) or repr(cb)
    )


def merge_dict(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Merge source dict into target dict.

    Args:
        target: Target dict (modified in place).
        source: Source dict.

    Raises:
        KeyConflictError: When target and source have overlapping keys.
    """
    conflicts = set(target.keys()) & set(source.keys())
    if conflicts:
        raise KeyConflictError(f"Key conflict: {conflicts}")
    target.update(source)
