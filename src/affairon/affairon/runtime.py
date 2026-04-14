"""Runtime registry and injection primitives.

Each :class:`~affairon.Node` owns a :class:`RuntimeRegistry` instance.
``provide(obj)`` stores an object keyed by its type; ``inject(Type)``
retrieves it.  This is how plain helper objects (clocks, configs, caches)
are shared within a node's scope without polluting the node's own attributes.

For ``@associate`` handlers, parameters with non-builtin type annotations
that are not already supplied by the caller are resolved automatically:

- Plain types (``Clock``) -- resolved via ``node.inject(Clock)``.
- ``Annotated[Clock, Root / Clock]`` -- resolved via the locator path,
  reaching into another node's registry.

The :func:`inject_from` decorator provides the same injection mechanism
for standalone functions outside the node system.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from inspect import BoundArguments, Signature, iscoroutinefunction, signature
from types import GenericAlias
from typing import (
    Annotated,
    Protocol,
    TypeVar,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from affairon.locator import Locator

_T = TypeVar("_T")


class _Injector(Protocol):
    def inject(self, key: type[object]) -> object: ...


class _LocatorInjector(_Injector, Protocol):
    def resolve(self, locator: Locator, expected_type: type[object]) -> object: ...


class RuntimeRegistry:
    def __init__(self) -> None:
        self._runtimes: dict[type[object], object] = {}

    def provide(self, runtime: _T) -> _T:
        self._runtimes[type(runtime)] = runtime
        return runtime

    def inject(self, key: type[_T]) -> _T:
        runtime = self._runtimes.get(key)
        if runtime is None:
            raise LookupError(f"{key.__name__} not provided")
        return cast(_T, runtime)


def _is_supported_runtime_annotation(annotation: object) -> bool:
    return isinstance(annotation, type) and annotation.__module__ != "builtins"


def _parse_annotation(annotation: object) -> tuple[type[object], Locator | None]:
    origin = get_origin(annotation)
    if origin is Annotated:
        args = cast(tuple[object, ...], get_args(annotation))
        runtime_candidate = args[0] if args else None
        if runtime_candidate is None:
            raise TypeError(f"Unsupported injected annotation: {annotation!r}")
        runtime_type = cast(type[object], runtime_candidate)
        if not _is_supported_runtime_annotation(runtime_type):
            raise TypeError(f"Unsupported injected annotation: {annotation!r}")
        locator = next(
            (
                cast(object, arg)
                for arg in args[1:]
                if isinstance(arg, Locator) or isinstance(arg, GenericAlias)
            ),
            None,
        )
        locator_obj = cast(Locator | None, locator)
        if locator_obj is None:
            raise TypeError(f"Annotated injection missing Locator: {annotation!r}")
        if locator_obj.segments[-1] is not runtime_type:
            raise TypeError(
                "Locator leaf must match annotated"
                + f" runtime type: {runtime_type.__name__}"
                + f" vs {locator_obj!r}"
            )
        return runtime_type, locator_obj

    if not _is_supported_runtime_annotation(annotation):
        raise TypeError(f"Unsupported injected annotation: {annotation!r}")
    return cast(type[object], annotation), None


def resolve_injected_kwargs(
    func: Callable[..., object],
    resolver: Callable[[type[object], Locator | None], object],
    bound_args: BoundArguments,
    *,
    local_only: bool,
) -> dict[str, object]:
    injected: dict[str, object] = {}
    hints = get_type_hints(func, include_extras=True)
    func_signature = signature(func)

    for name, parameter in func_signature.parameters.items():
        if name in bound_args.arguments:
            continue
        hint_value = cast(object, hints.get(name, cast(object, parameter.annotation)))
        annotation = hint_value
        if annotation is Signature.empty:
            continue

        runtime_type, locator = _parse_annotation(annotation)
        if local_only and locator is not None:
            raise TypeError(
                f"Explicit locators are not supported for local-only injection: {name}"
            )

        injected[name] = resolver(runtime_type, locator)

    return injected


def inject_from(
    injector_getter: Callable[..., object],
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    def decorator(func: Callable[..., object]) -> Callable[..., object]:
        getter_signature = signature(injector_getter)

        def resolve_injector(bound: BoundArguments) -> _Injector:
            getter_kwargs = {
                name: bound.arguments[name]
                for name in getter_signature.parameters
                if name in bound.arguments
            }
            injector = injector_getter(**getter_kwargs)
            if not hasattr(injector, "inject"):
                raise TypeError("injector_getter must return an injector-like object")
            return cast(_Injector, injector)

        def resolve_runtime(
            injector: _Injector,
            runtime_type: type[object],
            locator: Locator | None,
        ) -> object:
            if locator is not None:
                if not hasattr(injector, "resolve"):
                    raise TypeError(
                        f"Injector {type(injector).__name__} does not support locators"
                    )
                locator_injector = cast(_LocatorInjector, injector)
                return locator_injector.resolve(locator, runtime_type)
            return injector.inject(runtime_type)

        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: object, **kwargs: object) -> object:
                bound = signature(func).bind_partial(*args, **kwargs)
                injector = resolve_injector(bound)
                injected = resolve_injected_kwargs(
                    func,
                    lambda runtime_type, locator: resolve_runtime(
                        injector, runtime_type, locator
                    ),
                    bound,
                    local_only=False,
                )
                async_func = cast(Callable[..., Awaitable[object]], func)
                return await async_func(*args, **kwargs, **injected)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> object:
            bound = signature(func).bind_partial(*args, **kwargs)
            injector = resolve_injector(bound)
            injected = resolve_injected_kwargs(
                func,
                lambda runtime_type, locator: resolve_runtime(
                    injector, runtime_type, locator
                ),
                bound,
                local_only=False,
            )
            return func(*args, **kwargs, **injected)

        return sync_wrapper

    return decorator


__all__ = ["RuntimeRegistry", "inject_from", "resolve_injected_kwargs"]
