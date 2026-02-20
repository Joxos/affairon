from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

from affairon.affairs import MutableAffair
from affairon.aware import AffairAware
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
        callback: CB | AffairAware | None = None,
    ) -> None:
        """Unregister listeners.

        Supports four modes:
        - (*affair_types, callback=cb): Remove callback from specified types.
        - (*affair_types): Remove all listeners from specified types.
        - (callback=cb): Remove callback from all affair types.
        - (callback=instance): Remove all callbacks registered by an
          ``AffairAware`` instance on this dispatcher. If affair_types
          are given, only those types are affected.

        Args:
            *affair_types: MutableAffair types to remove from (variadic).
            callback: Callback, AffairAware instance, or None for all.

        Post:
            Matching listeners removed.

        Raises:
            ValueError: If no args provided.
        """
        if not affair_types and callback is None:
            raise ValueError("must provide affair_types or callback")

        # Instance-based unregistration: remove all callbacks belonging
        # to the AffairAware instance on this dispatcher.
        if isinstance(callback, AffairAware):
            self._unregister_instance(callback, affair_types or None)
            return

        normalized_types = list(affair_types) if affair_types else None
        self._registry.remove(normalized_types, callback)

    def _unregister_instance(
        self,
        instance: AffairAware,
        affair_types: tuple[type[MutableAffair], ...] | None = None,
    ) -> None:
        """Remove all callbacks registered by an AffairAware instance.

        Args:
            instance: AffairAware instance whose callbacks to remove.
            affair_types: If given, only remove from these affair types.
        """
        filter_types = set(affair_types) if affair_types else None
        for reg_disp, reg_types, reg_cb in instance._affair_registrations:
            if reg_disp is not self:
                continue
            if filter_types is not None:
                types_to_remove = [t for t in reg_types if t in filter_types]
            else:
                types_to_remove = reg_types
            if types_to_remove:
                self._registry.remove(types_to_remove, reg_cb)

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

    @staticmethod
    def _resolve_affair_types(
        affair: MutableAffair,
    ) -> list[type[MutableAffair]]:
        """Determine which affair types to dispatch for.

        When ``affair.emit_up`` is False, returns only the concrete type.
        When True, walks the MRO and returns all ``MutableAffair``
        subclasses from child to parent.

        Args:
            affair: The affair instance being emitted.

        Returns:
            Ordered list of affair types (child-first) to dispatch.
        """
        if not affair.emit_up:
            return [type(affair)]
        return [
            t
            for t in type(affair).__mro__
            if isinstance(t, type) and issubclass(t, MutableAffair)
        ]
