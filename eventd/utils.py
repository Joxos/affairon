from eventd.exceptions import KeyConflictError


from typing import Any


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
