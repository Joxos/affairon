"""AffairAware mixin for class-based callback registration.

Provides ``AffairAware`` (mixin) and ``AffairAwareMeta`` (metaclass)
that together enable automatic registration of ``@dispatcher.on_method()``
decorated class methods as affair callbacks.
"""

from types import TracebackType
from typing import Any

from loguru import logger

log = logger.bind(source=__name__)


class AffairAwareMeta(type):
    """Metaclass that registers ``@dispatcher.on_method()`` callbacks.

    Overrides ``__call__`` so that ``_bind_affair_methods()`` runs
    *after* ``__init__`` returns, regardless of whether the subclass
    calls ``super().__init__()``.
    """

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        instance = super().__call__(*args, **kwargs)
        instance._bind_affair_methods()
        return instance


class AffairAware(metaclass=AffairAwareMeta):
    """Mixin that auto-registers ``@dispatcher.on_method()`` decorated methods.

    Methods decorated with ``@dispatcher.on_method()`` inside an
    ``AffairAware`` subclass are not registered at class definition time.
    Instead, the decorator stamps metadata on the unbound function, and
    the ``AffairAwareMeta`` metaclass registers the *bound* methods
    automatically after ``__init__`` completes.

    Use ``on_method()`` (not ``on()``) for class methods.
    No ``super().__init__()`` call is required.

    Supports context manager protocol for scoped callback lifetime::

        with Handler("tag") as h:
            result = dispatcher.emit(Ping(msg="hi"))
        # callbacks automatically unregistered here

    For manual cleanup, call ``instance.unregister()``.

    ``@staticmethod`` and ``@classmethod`` are supported — place them
    **outside** ``@on_method()``:

    Example::

        class Kitchen(AffairAware):
            @dispatcher.on_method(AddIngredients)
            def cook(self, affair: AddIngredients) -> dict[str, list[str]]:
                return {"dish": ["eggs"]}

            @staticmethod
            @dispatcher.on_method(AddIngredients)
            def garnish(affair: AddIngredients) -> dict[str, str]:
                return {"garnish": "parsley"}

        k = Kitchen()  # cook() and garnish() are now registered
    """

    # Each tuple: (dispatcher, affair_types, bound_callback)
    _affair_registrations: list[tuple[Any, list[Any], Any]]

    def _bind_affair_methods(self) -> None:
        """Scan for marked methods and register them as bound callbacks."""
        self._affair_registrations = []

        # Collect marked methods across MRO, build unbound → bound mapping
        unbound_to_bound: dict[Any, Any] = {}
        marked: list[Any] = []

        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, attr in vars(klass).items():
                if name in seen:
                    continue
                # Unwrap staticmethod/classmethod to access inner function
                inner = attr
                if isinstance(attr, (staticmethod, classmethod)):
                    inner = attr.__func__
                if callable(inner) and hasattr(inner, "_affair_types"):
                    unbound_to_bound[inner] = getattr(self, name)
                    marked.append(inner)
                    seen.add(name)

        # Register each bound method, resolving after references
        for func in marked:
            bound = unbound_to_bound[func]
            after = func._affair_after
            if after:
                after = [unbound_to_bound.get(cb, cb) for cb in after]
            func._affair_dispatcher.register(func._affair_types, bound, after=after)
            self._affair_registrations.append(
                (func._affair_dispatcher, func._affair_types, bound)
            )

        if marked:
            log.debug(
                "Bound {} affair method(s) on {}",
                len(marked),
                type(self).__qualname__,
            )

    def unregister(self) -> None:
        """Unregister all callbacks bound by this instance.

        After calling, no callbacks registered by this instance will
        fire on future emits.  Safe to call multiple times.
        """
        for dispatcher, affair_types, callback in self._affair_registrations:
            try:
                dispatcher.unregister(*affair_types, callback=callback)
            except Exception:
                pass
        self._affair_registrations.clear()

    def __enter__(self) -> "AffairAware":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Unregister all callbacks registered by this instance."""
        self.unregister()
