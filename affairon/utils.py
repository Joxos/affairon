import re
from typing import Any

from affairon.affairs import MergeStrategy
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


def normalize_name(name: str) -> str:
    """Normalize a package/plugin name per PEP 503.

    Replaces any run of hyphens, underscores, or periods with a single
    hyphen and lower-cases the result, so that ``My_Plugin``,
    ``my-plugin``, and ``my.plugin`` all map to ``my-plugin``.

    Args:
        name: Raw plugin or package name.

    Returns:
        Normalized name string.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------


def _wrap_value(strategy: MergeStrategy, value: Any, source_name: str) -> Any:
    """Transform a value on first insertion based on merge strategy.

    For ``list_merge`` every value is stored as a single-element list;
    for ``dict_merge`` every value is stored as ``{source_name: value}``.
    Other strategies store the raw value.

    Args:
        strategy: Active merge strategy.
        value: Raw value from callback return dict.
        source_name: Callback display name.

    Returns:
        Wrapped value (list / dict) or original value.
    """
    match strategy:
        case "list_merge":
            return [value]
        case "dict_merge":
            return {source_name: value}
        case _:
            return value


def _resolve_conflict(
    strategy: MergeStrategy,
    key: str,
    existing: Any,
    new_value: Any,
    source_name: str,
) -> Any:
    """Resolve a key conflict between existing and new values.

    Args:
        strategy: Active merge strategy.
        key: The conflicting key.
        existing: Current value in target.
        new_value: Incoming value from source.
        source_name: Callback display name.

    Returns:
        Resolved value.

    Raises:
        KeyConflictError: When strategy is ``raise``.
    """
    match strategy:
        case "raise":
            raise KeyConflictError(f"Key conflict: {{'{key}'}}")
        case "keep":
            return existing
        case "override":
            return new_value
        case "list_merge":
            existing.append(new_value)
            return existing
        case "dict_merge":
            existing[source_name] = new_value
            return existing


def merge_dict(
    target: dict[str, Any],
    source: dict[str, Any],
    *,
    strategy: MergeStrategy = "raise",
    source_name: str = "",
) -> None:
    """Merge source dict into target dict using the given strategy.

    Args:
        target: Target dict (modified in place).
        source: Source dict.
        strategy: Conflict resolution strategy.
        source_name: Display name of the source callback (used by
            ``dict_merge`` strategy).

    Raises:
        KeyConflictError: When strategy is ``raise`` and keys overlap.
    """
    for key, value in source.items():
        if key in target:
            target[key] = _resolve_conflict(
                strategy, key, target[key], value, source_name
            )
        else:
            target[key] = _wrap_value(strategy, value, source_name)
