"""Shared type definitions for affairon.

All type aliases use PEP 695 ``type`` statement syntax.
``SyncCallback`` and ``AsyncCallback`` derive from ``StandardResult``
to avoid duplicating the result shape.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from affairon.affairs import MutableAffair

type StandardResult[V] = dict[str, V] | None
"""Generic result type for affair callbacks.

A callback may return a ``dict[str, V]`` whose entries are merged into
the final result, or ``None`` to contribute nothing.
"""

type SyncCallback = Callable[[MutableAffair], StandardResult[Any]]
"""Internal storage type for synchronous affair callbacks."""

type AsyncCallback = Callable[[MutableAffair], Coroutine[Any, Any, StandardResult[Any]]]
"""Internal storage type for asynchronous affair callbacks."""
