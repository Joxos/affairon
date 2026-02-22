import asyncio
from typing import Any

from loguru import logger

from affairon._types import AsyncCallback
from affairon.affairs import MutableAffair
from affairon.base_dispatcher import BaseDispatcher
from affairon.utils import callable_name, merge_dict

log = logger.bind(source=__name__)


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

        When ``affair.emit_up`` is True, callbacks registered on parent
        affair types are also invoked, walking the MRO from child to
        parent.

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
        merged_result: dict[str, Any] = {}
        affair_types = self._resolve_affair_types(affair)
        log.debug(
            "Emit {} (types={})",
            type(affair).__qualname__,
            [t.__qualname__ for t in affair_types],
        )
        for affair_type in affair_types:
            layers = self._registry.exec_order(affair_type)
            for layer in layers:
                tasks: list[asyncio.Task[dict[str, Any] | None]] = []
                filtered_cbs: list[AsyncCallback] = []
                async with asyncio.TaskGroup() as group:
                    for callback in layer:
                        if not self._registry.should_fire(
                            callback, affair_type, affair
                        ):
                            continue
                        filtered_cbs.append(callback)
                        tasks.append(group.create_task(callback(affair)))
                for cb, task in zip(filtered_cbs, tasks, strict=True):
                    result = task.result()
                    if result is not None:
                        if not isinstance(result, dict):
                            raise TypeError(
                                f"Callback {callable_name(cb)} returned "
                                f"{type(result).__name__}, expected dict or None"
                            )
                        merge_dict(merged_result, result)
        return merged_result
