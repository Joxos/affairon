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

from collections.abc import Callable
from functools import wraps
from inspect import BoundArguments, Signature, iscoroutinefunction, signature
from typing import Annotated, Any, TypeVar, cast, get_args, get_origin, get_type_hints

from affairon.locator import Locator

_T = TypeVar("_T")


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


def _is_supported_runtime_annotation(annotation: Any) -> bool:
    return isinstance(annotation, type) and annotation.__module__ != "builtins"


def _parse_annotation(annotation: Any) -> tuple[type[Any], Locator | None]:
    origin = get_origin(annotation)
    if origin is Annotated:
        args = get_args(annotation)
        runtime_type = args[0]
        if not _is_supported_runtime_annotation(runtime_type):
            raise TypeError(f"Unsupported injected annotation: {annotation!r}")
        locator = next((arg for arg in args[1:] if isinstance(arg, Locator)), None)
        if locator is None:
            raise TypeError(f"Annotated injection missing Locator: {annotation!r}")
        if locator.segments[-1] is not runtime_type:
            raise TypeError(
                "Locator leaf must match annotated runtime type: "
                f"{runtime_type.__name__} vs {locator!r}"
            )
        return runtime_type, locator

    if not _is_supported_runtime_annotation(annotation):
        raise TypeError(f"Unsupported injected annotation: {annotation!r}")
    return annotation, None


def _resolve_injected_kwargs(
    func: Callable[..., Any],
    resolver: Callable[[type[Any], Locator | None], Any],
    bound_args: BoundArguments,
    *,
    local_only: bool,
) -> dict[str, Any]:
    injected: dict[str, Any] = {}
    hints = get_type_hints(func, include_extras=True)
    func_signature = signature(func)

    for name, parameter in func_signature.parameters.items():
        if name in bound_args.arguments:
            continue
        annotation = hints.get(name, parameter.annotation)
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
    injector_getter: Callable[..., Any],
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        getter_signature = signature(injector_getter)

        def resolve_injector(bound: BoundArguments) -> Any:
            getter_kwargs = {
                name: bound.arguments[name]
                for name in getter_signature.parameters
                if name in bound.arguments
            }
            return injector_getter(**getter_kwargs)

        def resolve_runtime(
            injector: Any,
            runtime_type: type[Any],
            locator: Locator | None,
        ) -> Any:
            if locator is not None:
                if not hasattr(injector, "resolve"):
                    raise TypeError(
                        f"Injector {type(injector).__name__} does not support locators"
                    )
                return injector.resolve(locator, runtime_type)
            return injector.inject(runtime_type)

        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                bound = signature(func).bind_partial(*args, **kwargs)
                injector = resolve_injector(bound)
                injected = _resolve_injected_kwargs(
                    func,
                    lambda runtime_type, locator: resolve_runtime(
                        injector, runtime_type, locator
                    ),
                    bound,
                    local_only=False,
                )
                return await func(*args, **kwargs, **injected)

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature(func).bind_partial(*args, **kwargs)
            injector = resolve_injector(bound)
            injected = _resolve_injected_kwargs(
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


__all__ = ["RuntimeRegistry", "inject_from"]
