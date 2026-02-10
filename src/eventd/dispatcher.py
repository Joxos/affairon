"""Dispatcher implementations for event handling.

This module provides BaseDispatcher (abstract base), Dispatcher (sync),
and AsyncDispatcher (async) classes for event-driven programming.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from itertools import count
from typing import Any, TypeVar

from eventd._types import (
    AsyncListenerCallback,
    EventIdGenerator,
    ListenerCallback,
    TimestampGenerator,
)
from eventd.event import Event
from eventd.exceptions import KeyConflictError
from eventd.registry import ListenerEntry, RegistryTable

F = TypeVar("F", bound=Callable[..., Any])


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


class BaseDispatcher(ABC):
    """Abstract base class for event dispatchers.

    Provides common functionality for both sync and async dispatchers:
    - Listener registration/unregistration
    - Metadata injection (event_id, timestamp)
    - Registry management

    Subclasses must implement:
    - emit() - Event dispatching logic
    - shutdown() - Cleanup logic
    """

    def __init__(
        self,
        *,
        event_id_generator: EventIdGenerator | None = None,
        timestamp_generator: TimestampGenerator | None = None,
    ) -> None:
        """Initialize dispatcher.

        Args:
            event_id_generator: Function to generate event IDs
                (default: auto-increment).
            timestamp_generator: Function to generate timestamps
                (default: time.time).

        Post:
            Registry initialized, _is_shutting_down == False.
        """
        self._registry = RegistryTable()
        self._event_id_generator = event_id_generator or count().__next__
        self._timestamp_generator = timestamp_generator or time.time
        self._is_shutting_down = False

    def on(
        self,
        *event_types: type[Event],
        priority: int = 0,
        after: list[ListenerCallback] | None = None,
    ) -> Callable[[F], F]:
        """Decorator to register listener.

        Args:
            event_types: Event types to listen for.
            priority: Priority value (higher = executed first).
            after: List of callbacks that must execute before this one.

        Returns:
            Decorator function that returns the original function unchanged.

        Post:
            Callback registered to all specified event types.

        Raises:
            ValueError: If after references unregistered callback.
            CyclicDependencyError: If after forms a cycle.
        """

        def decorator(func: F) -> F:
            self.register(list(event_types), func, priority=priority, after=after)
            return func

        return decorator

    def register(
        self,
        event_types: type[Event] | list[type[Event]],
        callback: ListenerCallback,
        *,
        priority: int = 0,
        after: list[ListenerCallback] | None = None,
    ) -> None:
        """Register listener via method call.

        Args:
            event_types: Event type(s) to listen for.
            callback: Callback function.
            priority: Priority value (higher = executed first).
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
        entry = ListenerEntry(
            callback=callback, priority=priority, after=after or [], name=""
        )
        self._registry.add(normalized_types, entry)

    def unregister(
        self,
        event_types: type[Event] | list[type[Event]] | None = None,
        callback: ListenerCallback | None = None,
    ) -> None:
        """Unregister listeners.

        Supports four modes:
        - (event_types, callback): Remove callback from specified event types.
        - (event_types, None): Remove all listeners from specified event types.
        - (None, callback): Remove callback from all event types.
        - (None, None): ValueError.

        Args:
            event_types: Event types to remove from, or None for all.
            callback: Callback to remove, or None for all.

        Post:
            Matching listeners removed.

        Raises:
            ValueError: If both args are None, or callback not registered,
                        or removal breaks other listeners' after dependencies.
        """
        normalized_types = None
        if event_types is not None:
            normalized_types = (
                event_types if isinstance(event_types, list) else [event_types]
            )
        self._registry.remove(normalized_types, callback)

    @abstractmethod
    def emit(self, event: Event) -> dict[str, Any]:
        """Dispatch event to listeners.

        Args:
            event: Event to dispatch.

        Returns:
            Merged dict of all listener results.

        Post:
            event.event_id and event.timestamp set.
            All matching listeners executed in order.

        Raises:
            RuntimeError: If dispatcher is shut down.
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
        """
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        """Gracefully shut down dispatcher.

        Post:
            _is_shutting_down == True.
            Subsequent emit() calls will raise RuntimeError.
        """
        raise NotImplementedError

    def _inject_metadata(self, event: Event) -> None:
        """Inject event_id and timestamp into event.

        Args:
            event: Event to inject metadata into.

        Post:
            event.event_id and event.timestamp set.
        """
        object.__setattr__(event, "event_id", self._event_id_generator())
        object.__setattr__(event, "timestamp", self._timestamp_generator())


class Dispatcher(BaseDispatcher):
    """Synchronous event dispatcher.

    Executes listeners synchronously in priority order.
    Recursive emit() calls execute directly (no queue).
    """

    def emit(self, event: Event) -> dict[str, Any]:
        """Synchronously dispatch event.

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

        Raises:
            RuntimeError: If dispatcher is shut down.
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
        """
        if self._is_shutting_down:
            raise RuntimeError("Dispatcher is shut down")
        self._inject_metadata(event)
        return self._dispatch_single(event)

    def shutdown(self) -> None:
        """Gracefully shut down dispatcher.

        Idempotent: repeated calls are safe.

        Post:
            _is_shutting_down == True.
            Subsequent emit() calls will raise RuntimeError.
        """
        self._is_shutting_down = True

    def _dispatch_single(self, event: Event) -> dict[str, Any]:
        """Dispatch event to all matching listeners.

        Args:
            event: Event to dispatch.

        Returns:
            Merged dict of all listener results.
        """
        layers = self._registry.resolve_order(type(event))
        merged_result: dict[str, Any] = {}
        for layer in layers:
            for entry in layer:
                result = self._execute_listener(entry, event)
                if result is not None:
                    merge_dict(merged_result, result)
        return merged_result

    def _execute_listener(
        self, entry: ListenerEntry, event: Event
    ) -> dict[str, Any] | None:
        """Execute single listener.

        Args:
            entry: Listener entry to execute.
            event: Event to pass to listener.

        Returns:
            Listener result dict, or None.

        Raises:
            TypeError: If listener returns non-dict value.
        """
        result = entry.callback(event)
        if result is None:
            return None
        if not isinstance(result, dict):
            raise TypeError(
                f"Listener {entry.name} returned non-dict value: {type(result)}"
            )
        return result


class AsyncDispatcher(BaseDispatcher):
    """Asynchronous event dispatcher.

    Executes listeners asynchronously with same-priority parallelism.
    Uses asyncio.TaskGroup for structured concurrency.
    Recursive emit() calls execute directly (no queue).
    """

    def on(
        self,
        *event_types: type[Event],
        priority: int = 0,
        after: list[AsyncListenerCallback] | None = None,
    ) -> Callable[[F], F]:
        """Decorator to register async listener.

        Args:
            event_types: Event types to listen for.
            priority: Priority value (higher = executed first).
            after: List of callbacks that must execute before this one.

        Returns:
            Decorator function that returns the original function unchanged.

        Post:
            Callback registered to all specified event types.

        Raises:
            ValueError: If after references unregistered callback.
            CyclicDependencyError: If after forms a cycle.
        """

        def decorator(func: F) -> F:
            self.register(list(event_types), func, priority=priority, after=after)
            return func

        return decorator

    def register(
        self,
        event_types: type[Event] | list[type[Event]],
        callback: AsyncListenerCallback,
        *,
        priority: int = 0,
        after: list[AsyncListenerCallback] | None = None,
    ) -> None:
        """Register async listener via method call.

        Args:
            event_types: Event type(s) to listen for.
            callback: Async callback function.
            priority: Priority value (higher = executed first).
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
        entry = ListenerEntry(
            callback=callback,  # type: ignore[arg-type]
            priority=priority,
            after=after or [],  # type: ignore[arg-type]
            name="",
        )
        self._registry.add(normalized_types, entry)

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
            RuntimeError: If dispatcher is shut down.
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
            ExceptionGroup: If multiple listeners fail simultaneously.
        """
        if self._is_shutting_down:
            raise RuntimeError("Dispatcher is shut down")
        self._inject_metadata(event)
        return await self._dispatch_single(event)

    async def shutdown(self) -> None:
        """Gracefully shut down dispatcher.

        Idempotent: repeated calls are safe.

        Post:
            _is_shutting_down == True.
            Subsequent emit() calls will raise RuntimeError.
        """
        self._is_shutting_down = True

    async def _dispatch_single(self, event: Event) -> dict[str, Any]:
        """Dispatch event to all matching listeners with parallelism.

        Same-priority listeners execute in parallel via asyncio.TaskGroup.

        Args:
            event: Event to dispatch.

        Returns:
            Merged dict of all listener results.
        """
        layers = self._registry.resolve_order(type(event))
        merged_result: dict[str, Any] = {}
        for layer in layers:
            results: list[dict[str, Any] | None] = [None] * len(layer)

            try:
                async with asyncio.TaskGroup() as tg:
                    for i, entry in enumerate(layer):

                        async def _run(idx: int = i, e: ListenerEntry = entry) -> None:
                            results[idx] = await self._execute_listener(  # noqa: B023
                                e, event
                            )

                        tg.create_task(_run())
            except* Exception as eg:
                # If only one exception, unwrap and raise directly
                if len(eg.exceptions) == 1:
                    raise eg.exceptions[0] from None
                # Otherwise, let ExceptionGroup propagate
                raise

            for result in results:
                if result is not None:
                    merge_dict(merged_result, result)
        return merged_result

    async def _execute_listener(
        self, entry: ListenerEntry, event: Event
    ) -> dict[str, Any] | None:
        """Execute single async listener.

        Args:
            entry: Listener entry to execute.
            event: Event to pass to listener.

        Returns:
            Listener result dict, or None.

        Raises:
            TypeError: If listener returns non-dict value.
        """
        result = await entry.callback(event)  # type: ignore[misc]
        if result is None:
            return None
        if not isinstance(result, dict):
            raise TypeError(
                f"Listener {entry.name} returned non-dict value: {type(result)}"
            )
        return result
