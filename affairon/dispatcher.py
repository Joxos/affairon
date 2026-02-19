"""Synchronous dispatcher for affair handling."""

from typing import Any

from affairon._types import (
    SyncCallback,
)
from affairon.affairs import MutableAffair
from affairon.base_dispatcher import BaseDispatcher
from affairon.utils import merge_dict


class Dispatcher(BaseDispatcher[SyncCallback]):
    """Synchronous affair dispatcher.

    Executes listeners synchronously in priority order.
    Recursive emit() calls execute directly (no queue).
    """

    @staticmethod
    def _sample_guardian(affair: MutableAffair) -> None:
        """Silent guardian callback to anchor execution order."""

    def __init__(self):
        super().__init__(self._sample_guardian)

    def emit(self, affair: MutableAffair) -> dict[str, Any]:
        """Synchronously dispatch affair.

        Warning:
            Listeners can recursively call emit(). Framework does not detect cycles.
            Users must avoid infinite recursion chains (e.g., A→B→A), otherwise
            Python's RecursionError will be raised.

        Args:
            affair: MutableAffair to dispatch.

        Returns:
            Merged dict of all listener results.

        Post:
            affair.affair_id and affair.timestamp set.
            All matching listeners executed in priority order.

        Raises:
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
        """
        layers = self._registry.exec_order(type(affair))
        merged_result: dict[str, Any] = {}
        for layer in layers:
            for cb in layer:
                result = cb(affair)
                if result is not None:
                    merge_dict(merged_result, result)
        return merged_result
