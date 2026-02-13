"""Dispatcher implementations for event handling.

This module provides BaseDispatcher (abstract base), Dispatcher (sync),
and AsyncDispatcher (async) classes for event-driven programming.
"""

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from eventd._types import (
    AsyncCallbackT,
    CallbackT,
)
from eventd.event import Event
from eventd.exceptions import KeyConflictError
from eventd.registry import BaseRegistry


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


class BaseDispatcher[CB](ABC):
    """Abstract base class for event dispatchers.

    Provides common functionality for both sync and async dispatchers:
    - Listener registration/unregistration
    - Metadata injection (event_id, timestamp)
    - Registry management

    Subclasses must implement:
    - emit() - Event dispatching logic
    """

    _guardian: CB  # Guardian callback to anchor execution order
    _registry: BaseRegistry[CB]  # Registry for managing listeners

    def __init__(
        self,
        guardian: CB,
    ) -> None:
        """Initialize dispatcher."""
        self._guardian = guardian
        self._registry = BaseRegistry[CB](self._guardian)

    def on(
        self,
        *event_types: type[Event],
        after: list[CB] | None = None,
    ) -> Callable[[CB], CB]:
        """Decorator to register listener.

        Args:
            event_types: Event types to listen for.
            after: List of callbacks that must execute before this one.

        Returns:
            Decorator function that returns the original function unchanged.

        Post:
            Callback registered to all specified event types.

        Raises:
            ValueError: If after references unregistered callback.
            CyclicDependencyError: If after forms a cycle.
        """

        def decorator(func: CB) -> CB:
            self.register(list(event_types), func, after=after)  # type: ignore
            return func

        return decorator

    def register(
        self,
        event_types: type[Event] | list[type[Event]],
        callback: CB,
        *,
        after: list[CB] | None = None,
    ) -> None:
        """Register listener via method call.

        Args:
            event_types: Event type(s) to listen for.
            callback: Callback function.
            after: List of callbacks that must execute before this one.

        Post:
            Callback registered to all specified event types.

        Raises:
            ValueError: If after references unregistered callback.
            CyclicDependencyError: If after forms a cycle.
        """
        normalized_types = (
            event_types if isinstance(event_types, list) else [event_types]
        )
        self._registry.add(normalized_types, callback=callback, after=after)

    def unregister(
        self,
        *event_types: type[Event],
        callback: CB | None = None,
    ) -> None:
        """Unregister listeners.

        Supports three modes:
        - (*event_types, callback=cb): Remove callback from specified event types.
        - (*event_types): Remove all listeners from specified event types.
        - (callback=cb): Remove callback from all event types.

        Args:
            *event_types: Event types to remove from (variadic).
            callback: Callback to remove, or None for all.

        Post:
            Matching listeners removed.

        Raises:
            ValueError: If no args provided, or callback not registered,
                        or removal breaks other listeners' after dependencies.
        """
        if not event_types and callback is None:
            raise ValueError("must provide event_types or callback")

        normalized_types = list(event_types) if event_types else None
        self._registry.remove(normalized_types, callback)

    @abstractmethod
    def emit(self, event: Event) -> Any:
        """Dispatch event to listeners.

        Args:
            event: Event to dispatch.

        Returns:
            Merged dict of all listener results (sync or async).

        Post:
            event.event_id and event.timestamp set.
            All matching listeners executed in order.

        Raises:
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
        """
        raise NotImplementedError


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
