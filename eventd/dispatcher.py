"""Dispatcher implementations for event handling.

This module provides BaseDispatcher (abstract base), Dispatcher (sync),
and AsyncDispatcher (async) classes for event-driven programming.
"""

from typing import Any

from eventd._types import (
    CallbackT,
)
from eventd.base_dispatcher import BaseDispatcher
from eventd.event import Event
from eventd.utils import merge_dict


class Dispatcher(BaseDispatcher[CallbackT]):
    """Synchronous event dispatcher.

    Executes listeners synchronously in priority order.
    Recursive emit() calls execute directly (no queue).
    """

    @staticmethod
    def _sample_guardian(event: Event) -> None:
        """Silent guardian callback to anchor execution order."""

    def __init__(self):
        super().__init__(self._sample_guardian)

    def emit(self, event: Event) -> dict[str, Any]:
        """Synchronously dispatch event.

        Warning:
            Listeners can recursively call emit(). Framework does not detect cycles.
            Users must avoid infinite recursion chains (e.g., A→B→A), otherwise
            Python's RecursionError will be raised.

        Args:
            event: Event to dispatch.

        Returns:
            Merged dict of all listener results.

        Post:
            event.event_id and event.timestamp set.
            All matching listeners executed in priority order.

        Raises:
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
        """
        layers = self._registry.exec_order(type(event))
        merged_result: dict[str, Any] = {}
        for layer in layers:
            for cb in layer:
                result = cb(event)
                if result is not None:
                    merge_dict(merged_result, result)
        return merged_result


