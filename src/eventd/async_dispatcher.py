from eventd._types import AsyncCallbackT
from eventd.base_dispatcher import BaseDispatcher
from eventd.event import Event
from eventd.utils import merge_dict


import asyncio
from typing import Any


class AsyncDispatcher(BaseDispatcher[AsyncCallbackT]):
    """Asynchronous event dispatcher.

    Executes listeners asynchronously with same-priority parallelism.
    Uses asyncio.TaskGroup for structured concurrency.
    Recursive emit() calls execute directly (no queue).
    """

    @staticmethod
    async def _sample_guardian(event: Event) -> None:
        """Silent guardian callback to anchor execution order."""

    def __init__(self):
        super().__init__(self._sample_guardian)

    async def emit(self, event: Event) -> dict[str, Any]:
        """Asynchronously dispatch event.

        Warning:
            Listeners can recursively call emit(). Framework does not detect cycles.
            Users must avoid infinite recursion chains (e.g., A→B→A), otherwise
            Python's RecursionError will be raised (default stack depth: 1000).

        Args:
            event: Event to dispatch.

        Returns:
            Merged dict of all listener results.

        Post:
            event.event_id and event.timestamp set.
            All matching listeners executed in priority order.
            Same-priority listeners executed in parallel via TaskGroup.

        Raises:
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
            ExceptionGroup: If multiple listeners fail simultaneously.
        """
        layers = self._registry.exec_order(type(event))
        merged_result: dict[str, Any] = {}
        for layer in layers:
            tasks = []
            try:
                async with asyncio.TaskGroup() as tg:
                    for i, callback in enumerate(layer):
                        tasks.append(tg.create_task(callback(event)))
            except* Exception:
                # Let ExceptionGroup propagate
                raise
            else:
                for task in tasks:
                    result = task.result()
                    if result is not None:
                        merge_dict(merged_result, result)
        return merged_result