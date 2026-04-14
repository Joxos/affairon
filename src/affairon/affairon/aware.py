import inspect
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Protocol, cast, override, runtime_checkable

from loguru import logger

from affairon._types import AsyncCallback, SyncCallback
from affairon.affairs import MutableAffair
from affairon.listen import ListenSpec, get_listen_spec

log = logger.bind(source=__name__)


@runtime_checkable
class DispatcherLike(Protocol):
    def emit(self, affair: MutableAffair) -> object: ...

    def register(
        self,
        affair_types: type[MutableAffair] | list[type[MutableAffair]],
        callback: Callable[..., object],
        *,
        after: list[Callable[..., object]] | None = None,
        when: Callable[[MutableAffair], bool] | None = None,
    ) -> None: ...

    def unregister(
        self,
        *affair_types: type[MutableAffair],
        callback: Callable[..., object] | None = None,
    ) -> None: ...


def validate_listener_mode(dispatcher: DispatcherLike, callback: object) -> None:
    dispatcher_is_async = inspect.iscoroutinefunction(dispatcher.emit)
    callback_is_async = inspect.iscoroutinefunction(callback)

    if dispatcher_is_async == callback_is_async:
        return

    expected = "async" if dispatcher_is_async else "sync"
    actual = "async" if callback_is_async else "sync"
    callback_name = getattr(callback, "__qualname__", type(callback).__qualname__)
    raise TypeError(
        f"{callback_name} is {actual}, but "
        + f"{type(dispatcher).__qualname__}"
        + f" requires {expected} callbacks"
    )


class AffairAwareMeta(type):
    @override
    def __call__(cls, *args: object, **kwargs: object) -> object:
        dispatcher = kwargs.pop("dispatcher", None)
        instance = cast(object, super().__call__(*args, **kwargs))
        if isinstance(instance, AffairAware):
            instance.bind_affair_methods(cast(DispatcherLike | None, dispatcher))
        return instance


class AffairAware(metaclass=AffairAwareMeta):
    _affair_registrations: list[
        tuple[DispatcherLike, list[type[MutableAffair]], SyncCallback | AsyncCallback]
    ] = []

    def bind_affair_methods(self, dispatcher: DispatcherLike | None) -> None:
        self._affair_registrations = []

        unbound_to_bound: dict[object, Callable[..., object]] = {}
        specs: list[tuple[object, Callable[..., object], ListenSpec]] = []

        seen: set[str] = set()
        for klass in type(self).__mro__:
            namespace = cast(Mapping[str, object], vars(klass))
            for name, attr in namespace.items():
                if name in seen:
                    continue
                inner: object = attr
                if isinstance(attr, (staticmethod, classmethod)):
                    inner = cast(Callable[..., object], attr.__func__)
                spec = get_listen_spec(inner)
                if callable(inner) and spec is not None:
                    bound: object = getattr(self, name)  # pyright: ignore[reportAny]
                    if not callable(bound):
                        continue
                    unbound_to_bound[inner] = bound
                    specs.append((inner, bound, spec))
                    seen.add(name)

        if not specs:
            return

        if dispatcher is None:
            raise ValueError(f"{type(self).__qualname__} requires dispatcher=...")

        try:
            for _func, bound, spec in specs:
                validate_listener_mode(dispatcher, bound)
                after_raw = spec.after
                after_cbs: list[Callable[..., object]] | None = None
                if after_raw:
                    after_cbs = [
                        unbound_to_bound.get(cb, cb)
                        for cb in cast(list[Callable[..., object]], after_raw)
                    ]
                dispatcher.register(
                    spec.affair_types, bound, after=after_cbs, when=spec.when
                )
                self._affair_registrations.append(
                    (
                        dispatcher,
                        spec.affair_types,
                        cast(SyncCallback | AsyncCallback, bound),
                    )
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
        self.unregister()


__all__ = [
    "AffairAware",
    "AffairAwareMeta",
    "DispatcherLike",
    "validate_listener_mode",
]
