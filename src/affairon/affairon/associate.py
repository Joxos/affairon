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

from collections.abc import Awaitable, Callable, Mapping
from functools import wraps
from inspect import BoundArguments, iscoroutinefunction, signature
from typing import Protocol, cast

from pydantic import create_model

from affairon.affairs import MutableAffair
from affairon.listen import LISTEN_SPEC_ATTR, ListenSpec
from affairon.runtime import resolve_injected_kwargs

ASSOCIATE_SPEC_ATTR = "_affair_associate_spec"


class AffairPlaceholder:
    """Sentinel returned by ``affair()`` to mark an affair slot.

    During class creation, :class:`~affairon.node.NodeMeta` replaces each
    placeholder with the generated ``MutableAffair`` subclass produced by
    the matching ``@associate`` handler.
    """

    def __init__(self, name: str | None = None) -> None:
        self.name: str | None = name


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
    return AffairPlaceholder()  # pyright: ignore[reportReturnType]  # type: ignore[return-value]


class AssociateSpec:
    affair_type: type[MutableAffair]
    callback: Callable[..., object]
    expose_as: str | None
    placeholder: AffairPlaceholder | None

    def __init__(
        self,
        affair_type: type[MutableAffair],
        callback: Callable[..., object],
        expose_as: str | None,
        placeholder: AffairPlaceholder | None,
    ) -> None:
        self.affair_type = affair_type
        self.callback = callback
        self.expose_as = expose_as
        self.placeholder = placeholder


def _build_generated_affair(
    func: Callable[..., object],
    affair_type: type[MutableAffair] | AffairPlaceholder,
) -> type[MutableAffair]:
    if isinstance(affair_type, type):
        return affair_type
    generated_name = affair_type.name or f"{func.__qualname__.replace('.', '')}Affair"

    field_definitions: dict[str, object] = {"node": (object, ...)}
    for name, parameter in signature(func).parameters.items():
        if name == "self":
            continue
        default = cast(object, parameter.default)
        if default is not parameter.empty:
            continue
        annotation = cast(object, parameter.annotation)
        if annotation is parameter.empty:
            raise TypeError(
                f"Cannot generate affair field for '{name}' without annotation"
            )
        if name == "affair":
            continue
        field_definitions[name] = (annotation, ...)

    generated: type[MutableAffair] = cast(
        type[MutableAffair],
        create_model(generated_name, __base__=MutableAffair, **field_definitions),  # pyright: ignore[reportCallIssue,reportArgumentType]
    )
    return generated


def rename_generated_affair(
    affair_type: type[MutableAffair],
    name: str,
) -> type[MutableAffair]:
    affair_type.__name__ = name
    affair_type.__qualname__ = name
    return affair_type


def get_associate_spec(obj: object) -> AssociateSpec | None:
    spec = getattr(obj, ASSOCIATE_SPEC_ATTR, None)
    if isinstance(spec, AssociateSpec):
        return spec
    return None


def iter_associate_specs(cls: type[object]) -> list[tuple[str, AssociateSpec]]:
    specs: list[tuple[str, AssociateSpec]] = []
    seen: set[str] = set()
    for klass in cls.__mro__:
        namespace = cast(Mapping[str, object], vars(klass))
        for name, attr in namespace.items():
            if name in seen:
                continue
            inner: object = attr
            if isinstance(attr, (staticmethod, classmethod)):
                inner = cast(Callable[..., object], attr.__func__)
            spec = get_associate_spec(inner)
            if spec is None:
                continue
            specs.append((name, spec))
            seen.add(name)
    return specs


def associate(
    affair_type: object,
    *,
    expose_as: str | None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
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

    if not isinstance(affair_type, AffairPlaceholder) and not (
        isinstance(affair_type, type) and issubclass(affair_type, MutableAffair)
    ):
        raise TypeError(
            "@associate expects an affair() placeholder or MutableAffair subclass"
        )
    typed_affair_type = affair_type

    class _AssociateNode(Protocol):
        def resolve(self, locator: object, expected_type: type[object]) -> object: ...

        def inject(self, key: type[object]) -> object: ...

    def decorator(func: Callable[..., object]) -> Callable[..., object]:
        placeholder = (
            typed_affair_type
            if isinstance(typed_affair_type, AffairPlaceholder)
            else None
        )
        generated_affair = _build_generated_affair(func, typed_affair_type)

        def resolve_for_associate(bound: BoundArguments) -> _AssociateNode:
            if "self" not in bound.arguments:
                raise TypeError("@associate methods require 'self'")
            return cast(_AssociateNode, bound.arguments["self"])

        def resolve_affair(bound: BoundArguments) -> object | None:
            return bound.arguments.get("affair")

        def resolver(
            runtime_type: type[object],
            locator: object | None,
            *,
            node: _AssociateNode,
        ) -> object:
            if locator is not None:
                return node.resolve(locator, runtime_type)
            return node.inject(runtime_type)

        if iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: object, **kwargs: object) -> object:
                bound = signature(func).bind_partial(*args, **kwargs)
                node = resolve_for_associate(bound)
                affair = resolve_affair(bound)
                injected = resolve_injected_kwargs(
                    func,
                    lambda runtime_type, locator: resolver(
                        runtime_type, locator, node=node
                    ),
                    bound,
                    local_only=False,
                )
                if "affair" not in bound.arguments and affair is not None:
                    injected["affair"] = affair
                async_func = cast(Callable[..., Awaitable[object]], func)
                return await async_func(*args, **kwargs, **injected)

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
        def sync_wrapper(*args: object, **kwargs: object) -> object:
            bound = signature(func).bind_partial(*args, **kwargs)
            node = resolve_for_associate(bound)
            affair = resolve_affair(bound)
            injected = resolve_injected_kwargs(
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
    "rename_generated_affair",
    "affair",
    "associate",
    "get_associate_spec",
    "iter_associate_specs",
]
