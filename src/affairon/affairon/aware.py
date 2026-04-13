import inspect
from types import TracebackType
from typing import Any

from loguru import logger

from affairon.listen import get_listen_spec

log = logger.bind(source=__name__)


def _validate_listener_mode(dispatcher: Any, callback: Any) -> None:
    dispatcher_is_async = inspect.iscoroutinefunction(dispatcher.emit)
    callback_is_async = inspect.iscoroutinefunction(callback)

    if dispatcher_is_async == callback_is_async:
        return

    expected = "async" if dispatcher_is_async else "sync"
    actual = "async" if callback_is_async else "sync"
    raise TypeError(
        f"{callback.__qualname__} is {actual}, but {type(dispatcher).__qualname__} "
        f"requires {expected} callbacks"
    )


class AffairAwareMeta(type):
    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        dispatcher = kwargs.pop("dispatcher", None)
        instance = super().__call__(*args, **kwargs)
        instance._bind_affair_methods(dispatcher)
        return instance


class AffairAware(metaclass=AffairAwareMeta):
    # Each tuple: (dispatcher, affair_types, bound_callback)
    _affair_registrations: list[tuple[Any, list[Any], Any]]

    def _bind_affair_methods(self, dispatcher: Any) -> None:
        self._affair_registrations = []

        unbound_to_bound: dict[Any, Any] = {}
        specs: list[tuple[Any, Any, Any]] = []

        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, attr in vars(klass).items():
                if name in seen:
                    continue
                inner = attr
                if isinstance(attr, (staticmethod, classmethod)):
                    inner = attr.__func__
                spec = get_listen_spec(inner)
                if callable(inner) and spec is not None:
                    bound = getattr(self, name)
                    unbound_to_bound[inner] = bound
                    specs.append((inner, bound, spec))
                    seen.add(name)

        if not specs:
            return

        if dispatcher is None:
            raise ValueError(f"{type(self).__qualname__} requires dispatcher=...")

        try:
            for _func, bound, spec in specs:
                _validate_listener_mode(dispatcher, bound)
                after = spec.after
                if after:
                    after = [unbound_to_bound.get(cb, cb) for cb in after]
                dispatcher.register(
                    spec.affair_types, bound, after=after, when=spec.when
                )
                self._affair_registrations.append(
                    (dispatcher, spec.affair_types, bound)
                )
        except Exception:
            self.unregister()
            raise

        log.debug(
            "Bound {} affair method(s) on {}",
            len(specs),
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
