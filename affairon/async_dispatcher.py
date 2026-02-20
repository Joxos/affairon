import asyncio
from typing import Any

from affairon._types import AsyncCallback
from affairon.affairs import MutableAffair
from affairon.base_dispatcher import BaseDispatcher
from affairon.utils import merge_dict


class AsyncDispatcher(BaseDispatcher[AsyncCallback]):
    """Asynchronous affair dispatcher.

    Executes listeners asynchronously with same-priority parallelism.
    Uses asyncio.TaskGroup for structured concurrency.
    Recursive emit() calls execute directly (no queue).
    """

    @staticmethod
    async def _sample_guardian(affair: MutableAffair) -> None:
        """Silent guardian callback to anchor execution order."""

    def __init__(self):
        super().__init__(self._sample_guardian)

    async def emit(self, affair: MutableAffair) -> dict[str, Any]:
        """Asynchronously dispatch affair.

        Warning:
            Listeners can recursively call emit(). Framework does not detect cycles.
            Users must avoid infinite recursion chains (e.g., A→B→A), otherwise
            Python's RecursionError will be raised (default stack depth: 1000).

        Args:
            affair: MutableAffair to dispatch.

        Returns:
            Merged dict of all listener results.

        Post:
            All matching listeners executed in priority order.
            Same-priority listeners executed in parallel via TaskGroup.

        Raises:
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
            ExceptionGroup: If multiple listeners fail simultaneously.
        """
        layers = self._registry.exec_order(type(affair))
        merged_result: dict[str, Any] = {}
        for layer in layers:
            tasks: list[asyncio.Task[dict[str, Any] | None]] = []
            async with asyncio.TaskGroup() as group:
                for callback in layer:
                    tasks.append(group.create_task(callback(affair)))
            for task in tasks:
                result = task.result()
                if result is not None:
                    merge_dict(merged_result, result)
        return merged_result
