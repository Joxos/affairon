"""Affair association: binding node methods to generated affairs.

This module provides the ``affair()`` factory and the ``@associate`` decorator.
Together they let a node class declare an affair slot and bind a handler in
two lines::

    class Counter(Node):
        IncrementAffair = affair()

        @associate(IncrementAffair)
        def increment(self, amount: int) -> dict[str, int]:
            ...

``affair()`` returns an :class:`AffairPlaceholder`.  When
:class:`~affairon.node.NodeMeta` processes the class, it sees that
``@associate(IncrementAffair)`` targets that placeholder and generates a
``MutableAffair`` subclass with fields inferred from the handler's signature
(here: ``node: object, amount: int``).  The generated class is written back
to ``Counter.IncrementAffair``, replacing the placeholder.

The handler works as both a dispatcher-triggered callback (when the tree is
connected to a :class:`~affairon.Dispatcher`) and a plain method call
(``counter.increment(5)``).
"""

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
    """Sentinel returned by ``affair()`` to mark an affair slot.

    During class creation, :class:`~affairon.node.NodeMeta` replaces each
    placeholder with the generated ``MutableAffair`` subclass produced by
    the matching ``@associate`` handler.
    """

    def __init__(self, name: str | None = None) -> None:
        self.name = name


def affair() -> type[MutableAffair]:
    """Declare an affair slot on a node class.

    Works like ``enum.auto()`` -- call it in the class body, assign to a
    class variable, and pair it with ``@associate``::

        class MyNode(Node):
            DoSomethingAffair = affair()

            @associate(DoSomethingAffair)
            def do_something(self, x: int) -> dict[str, int]:
                return {"x": x}

    The placeholder is replaced with a real ``MutableAffair`` subclass
    after the class is created.  The generated affair has fields inferred
    from the handler's parameter signature.
    """
    return AffairPlaceholder()  # type: ignore[return-value]


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
    if isinstance(affair_type, type) and issubclass(affair_type, MutableAffair):
        return affair_type
    if not isinstance(affair_type, AffairPlaceholder):
        raise TypeError(
            f"@associate expects an affair() placeholder or a MutableAffair subclass, "
            f"got {affair_type!r}"
        )
    generated_name = affair_type.name or f"{func.__qualname__.replace('.', '')}Affair"

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
    """Bind a node method as the handler for *affair_type*.

    *affair_type* is either an ``affair()`` placeholder or a concrete
    ``MutableAffair`` subclass.  When the node tree is connected to a
    dispatcher, the decorated method is auto-registered as a listener.
    The method can also be called directly as a plain method.

    Parameters annotated with ``Annotated[T, Root / T]`` or similar locator
    expressions are injected automatically -- both when called via the
    dispatcher and when called directly.

    Args:
        affair_type: An ``affair()`` placeholder or ``MutableAffair`` subclass.
        expose_as: Optional name to expose the generated affair class as a
            class attribute on the node.
    """

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
    "affair",
    "associate",
    "get_associate_spec",
    "iter_associate_specs",
]
