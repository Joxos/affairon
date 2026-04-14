from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from inspect import BoundArguments, iscoroutinefunction, signature
from typing import Any

from pydantic import create_model

from affairon.affairs import MutableAffair
from affairon.listen import LISTEN_SPEC_ATTR, ListenSpec
from affairon.runtime import _resolve_injected_kwargs

ASSOCIATE_SPEC_ATTR = "_affair_associate_spec"


class AffairPlaceholder:
    def __init__(self, name: str) -> None:
        self.name = name


class AssociateSpec:
    def __init__(
        self,
        affair_type: type[MutableAffair],
        callback: Callable[..., Any],
        expose_as: str | None,
        placeholder: AffairPlaceholder | None,
    ) -> None:
        self.affair_type = affair_type
        self.callback = callback
        self.expose_as = expose_as
        self.placeholder = placeholder


def _build_generated_affair(
    func: Callable[..., Any],
    affair_type: type[Any],
) -> type[MutableAffair]:
    if isinstance(affair_type, AffairPlaceholder):
        generated_name = affair_type.name
    elif isinstance(affair_type, type) and issubclass(affair_type, MutableAffair):
        return affair_type
    else:
        generated_name = (
            affair_type.__name__
            if isinstance(affair_type, type)
            else f"{func.__qualname__.replace('.', '')}Affair"
        )

    field_definitions: dict[str, Any] = {"node": (object, ...)}
    for name, parameter in signature(func).parameters.items():
        if name == "self":
            continue
        if parameter.default is not parameter.empty:
            continue
        if parameter.annotation is parameter.empty:
            raise TypeError(
                f"Cannot generate affair field for '{name}' without annotation"
            )
        if name == "affair":
            continue
        field_definitions[name] = (parameter.annotation, ...)

    return create_model(  # type: ignore[return-value]
        generated_name,
        __base__=MutableAffair,
        **field_definitions,
    )


def _rename_generated_affair(
    affair_type: type[MutableAffair],
    name: str,
) -> type[MutableAffair]:
    affair_type.__name__ = name
    affair_type.__qualname__ = name
    return affair_type


def get_associate_spec(obj: Any) -> AssociateSpec | None:
    spec = getattr(obj, ASSOCIATE_SPEC_ATTR, None)
    if isinstance(spec, AssociateSpec):
        return spec
    return None


def iter_associate_specs(cls: type[Any]) -> list[tuple[str, AssociateSpec]]:
    specs: list[tuple[str, AssociateSpec]] = []
    seen: set[str] = set()
    for klass in cls.__mro__:
        for name, attr in vars(klass).items():
            if name in seen:
                continue
            inner = attr
            if isinstance(attr, (staticmethod, classmethod)):
                inner = attr.__func__
            spec = get_associate_spec(inner)
            if spec is None:
                continue
            specs.append((name, spec))
            seen.add(name)
    return specs


def associate(
    affair_type: type[Any],
    *,
    expose_as: str | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        placeholder = (
            affair_type if isinstance(affair_type, AffairPlaceholder) else None
        )
        generated_affair = _build_generated_affair(func, affair_type)

        def resolve_for_associate(bound: BoundArguments) -> Any:
            if "self" not in bound.arguments:
                raise TypeError("@associate methods require 'self'")
            return bound.arguments["self"]

        def resolve_affair(bound: BoundArguments) -> Any | None:
            return bound.arguments.get("affair")

        def resolver(runtime_type: type[Any], locator: Any, *, node: Any) -> Any:
            if locator is not None:
                return node.resolve(locator, runtime_type)
            return node.inject(runtime_type)

        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                bound = signature(func).bind_partial(*args, **kwargs)
                node = resolve_for_associate(bound)
                affair = resolve_affair(bound)
                injected = _resolve_injected_kwargs(
                    func,
                    lambda runtime_type, locator: resolver(
                        runtime_type, locator, node=node
                    ),
                    bound,
                    local_only=False,
                )
                if "affair" not in bound.arguments and affair is not None:
                    injected["affair"] = affair
                return await func(*args, **kwargs, **injected)

            setattr(
                async_wrapper,
                ASSOCIATE_SPEC_ATTR,
                AssociateSpec(generated_affair, async_wrapper, expose_as, placeholder),
            )
            setattr(
                async_wrapper,
                LISTEN_SPEC_ATTR,
                ListenSpec(affair_types=[generated_affair], after=None, when=None),
            )

            return async_wrapper

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature(func).bind_partial(*args, **kwargs)
            node = resolve_for_associate(bound)
            affair = resolve_affair(bound)
            injected = _resolve_injected_kwargs(
                func,
                lambda runtime_type, locator: resolver(
                    runtime_type, locator, node=node
                ),
                bound,
                local_only=False,
            )
            if "affair" not in bound.arguments and affair is not None:
                injected["affair"] = affair
            return func(*args, **kwargs, **injected)

        setattr(
            sync_wrapper,
            ASSOCIATE_SPEC_ATTR,
            AssociateSpec(generated_affair, sync_wrapper, expose_as, placeholder),
        )
        setattr(
            sync_wrapper,
            LISTEN_SPEC_ATTR,
            ListenSpec(affair_types=[generated_affair], after=None, when=None),
        )

        return sync_wrapper

    return decorator


__all__ = [
    "ASSOCIATE_SPEC_ATTR",
    "AffairPlaceholder",
    "AssociateSpec",
    "_rename_generated_affair",
    "associate",
    "get_associate_spec",
    "iter_associate_specs",
]
