from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from affairon.affairs import MutableAffair
from affairon.registry import BaseRegistry


class BaseDispatcher[CB](ABC):
    """Abstract base class for affair dispatchers.

    Provides common functionality for both sync and async dispatchers:
    - Listener registration/unregistration
    - Registry management

    Subclasses must implement:
    - emit() - Affair dispatching logic
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

    def on[A: MutableAffair, R: (dict[str, Any] | None)](
        self,
        *affair_types: type[A],
        after: list[Callable[[A], R]] | None = None,
    ) -> Callable[[Callable[[A], R]], Callable[[A], R]]:
        """Decorator to register a plain function as listener.

        Registers the callback immediately.  For class methods, use
        :meth:`on_method` instead so the bound method is registered at
        instantiation time via :class:`AffairAwareMeta`.

        Args:
            affair_types: MutableAffair types to listen for.
            after: List of callbacks that must execute before this one.

        Returns:
            Decorator function that returns the original function unchanged.

        Post:
            Callback registered to all specified affair types.

        Raises:
            ValueError: If after references unregistered callback.
            CyclicDependencyError: If after forms a cycle.
        """

        def decorator(func: Callable[[A], R]) -> Callable[[A], R]:
            self.register(list(affair_types), func, after=after)  # type: ignore[arg-type]
            return func

        return decorator

    def on_method[A: MutableAffair, F: Callable[..., Any]](
        self,
        *affair_types: type[A],
        after: list[Any] | None = None,
    ) -> Callable[[F], F]:
        """Decorator to mark a class method for deferred registration.

        Does **not** register the callback.  Instead it stamps metadata
        on the unbound function so that :class:`AffairAwareMeta` can
        register the *bound* method when the owning class is instantiated.

        Must be used inside an :class:`AffairAware` subclass.

        Args:
            affair_types: MutableAffair types to listen for.
            after: List of callbacks that must execute before this one.

        Returns:
            Decorator function that returns the original function unchanged.

        Post:
            ``_affair_types``, ``_affair_after``, ``_affair_dispatcher``
            stamped on the function for later consumption by the metaclass.
        """

        def decorator(func: F) -> F:
            func._affair_types = list(affair_types)  # type: ignore[attr-defined]
            func._affair_after = after  # type: ignore[attr-defined]
            func._affair_dispatcher = self  # type: ignore[attr-defined]
            return func

        return decorator

    def register(
        self,
        affair_types: type[MutableAffair] | list[type[MutableAffair]],
        callback: CB,
        *,
        after: list[CB] | None = None,
    ) -> None:
        """Register listener via method call.

        Args:
            affair_types: MutableAffair type(s) to listen for.
            callback: Callback function.
            after: List of callbacks that must execute before this one.

        Post:
            Callback registered to all specified affair types.

        Raises:
            ValueError: If after references unregistered callback.
            CyclicDependencyError: If after forms a cycle.
        """
        normalized_types = (
            affair_types if isinstance(affair_types, list) else [affair_types]
        )
        self._registry.add(normalized_types, callback=callback, after=after)

    def unregister(
        self,
        *affair_types: type[MutableAffair],
        callback: CB | None = None,
    ) -> None:
        """Unregister listeners.

        Supports three modes:
        - (*affair_types, callback=cb): Remove callback from specified affair types.
        - (*affair_types): Remove all listeners from specified affair types.
        - (callback=cb): Remove callback from all affair types.

        Args:
            *affair_types: MutableAffair types to remove from (variadic).
            callback: Callback to remove, or None for all.

        Post:
            Matching listeners removed.

        Raises:
            ValueError: If no args provided, or callback not registered,
                        or removal breaks other listeners' after dependencies.
        """
        if not affair_types and callback is None:
            raise ValueError("must provide affair_types or callback")

        normalized_types = list(affair_types) if affair_types else None
        self._registry.remove(normalized_types, callback)

    @abstractmethod
    def emit(self, affair: MutableAffair) -> Any:
        """Dispatch affair to listeners.

        Args:
            affair: MutableAffair to dispatch.

        Returns:
            Merged dict of all listener results (sync or async).

        Post:
            All matching listeners executed in order.

        Raises:
            TypeError: If listener returns non-dict value.
            KeyConflictError: If merging dicts causes key conflict.
            RecursionError: If listeners form infinite recursion chain.
        """
        raise NotImplementedError
