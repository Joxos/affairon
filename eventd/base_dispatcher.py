from eventd.event import Event
from eventd.registry import BaseRegistry


from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


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