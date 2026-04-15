"""Node tree: hierarchical state composition on top of the affair dispatch layer.

A node tree is a parent-child hierarchy where each node owns its own state,
declares affairs via ``affair()``, and wires handlers via ``@associate``.
The tree connects to a :class:`~affairon.Dispatcher` through
:meth:`Node.attach_dispatcher`, which recursively registers every
``@associate`` handler as a dispatcher listener.

Key concepts
------------
- **Node** -- base class that holds state, children, and a local
  :class:`~affairon.RuntimeRegistry`.
- **@route("name")** -- names a node class so it can be mounted as a child
  under that attribute name.
- **@root** -- marks a node class as a tree root.  Root nodes auto-mount any
  children declared with ``inject_to()``.
- **inject_to(Parent)** -- declares a node class as an auto-mounted child of
  *Parent*.  Replaces the old ``@Parent.inject`` decorator, which was removed
  because the method name collided with ``Node.inject()`` (the runtime-registry
  lookup).  ``inject_to`` is a plain module-level function, so there is no
  ambiguity.
- **provide(obj) / inject(Type)** -- per-node runtime registry.  ``provide``
  stores an object keyed by its type; ``inject`` retrieves it.  This is how
  helper objects (clocks, configs, caches) are shared within a node's scope.
  Locators can reach into other nodes' registries when needed.
- **attach_dispatcher(d)** -- connects the whole tree to a dispatcher,
  recursively binding all ``@associate`` handlers.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from typing import Protocol, Self, TypeVar, cast, override

from affairon._types import SyncCallback
from affairon.affairs import MutableAffair
from affairon.associate import (
    AffairPlaceholder,
    get_associate_spec,
    iter_associate_specs,
    rename_generated_affair,
)
from affairon.aware import validate_listener_mode
from affairon.dispatcher import Dispatcher
from affairon.locator import Locator, Parent, Root
from affairon.runtime import RuntimeRegistry

_T = TypeVar("_T")
_C = TypeVar("_C")
_N = TypeVar("_N", bound="Node")
ROUTE_ATTR = "_affair_route_name"
INJECT_PARENT_ATTR = "_affair_inject_parent"
ROOT_MARK_ATTR = "_affair_root_marked"
AUTO_CHILDREN_ATTR = "_affair_auto_children"


def route(name: str) -> Callable[[_C], _C]:
    """Name a node class for mounting.

    The route name becomes the attribute name on the parent node::

        @route("counter")
        class Counter(Node): ...

        root.mount(Counter())  # accessible as root.counter
    """

    def decorator(obj: _C) -> _C:
        setattr(obj, ROUTE_ATTR, name)
        return obj

    return decorator


def root[N: Node](node_type: type[N]) -> type[N]:
    """Mark a node class as a tree root.

    Root nodes automatically instantiate and mount any children declared
    with ``inject_to()`` during ``__init__``::

        @root
        @route("app")
        class App(Node): ...

        @inject_to(App)
        @route("counter")
        class Counter(Node): ...

        app = App()        # Counter() is already mounted as app.counter
    """
    setattr(node_type, ROOT_MARK_ATTR, True)
    return node_type


def inject_to(parent_type: type[Node]) -> Callable[[type[_N]], type[_N]]:
    """Declare a node class as an auto-mounted child of *parent_type*.

    When the parent is instantiated as a root (or is itself mounted into
    a tree), every ``inject_to`` child is created with a zero-arg constructor
    and mounted under its ``@route`` name.

    This replaced the earlier ``@Parent.inject`` decorator.  That API was
    removed because ``inject`` on a class returned a decorator, while
    ``inject`` on an instance performed a runtime-registry lookup -- the
    overloaded name confused both readers and type checkers.  ``inject_to``
    is a plain function with no ambiguity::

        @inject_to(MemberList)
        @route("stats")
        class MemberStats(Node): ...
    """

    def decorator(node_type: type[_N]) -> type[_N]:
        setattr(node_type, INJECT_PARENT_ATTR, parent_type)
        children = cast(
            list[type[_N]] | None, getattr(parent_type, AUTO_CHILDREN_ATTR, None)
        )
        if children is None:
            children = []
            setattr(parent_type, AUTO_CHILDREN_ATTR, children)
        _ = children.append(node_type)
        return node_type

    return decorator


def _backfill_declared_affair_placeholders(node_type: type[object]) -> None:
    placeholders = cast(
        dict[str, AffairPlaceholder], getattr(node_type, "_affair_placeholders", {})
    )
    placeholder_names = list(placeholders)
    associate_specs = iter_associate_specs(node_type)
    if not placeholder_names:
        return

    claimed_by_identity: set[str] = set()
    for _method_name, spec in associate_specs:
        placeholder = spec.placeholder
        if placeholder is None:
            continue
        placeholder_name = placeholder.name
        if placeholder_name is None:
            continue
        expected = placeholders.get(placeholder_name)
        if expected is None:
            continue
        if expected is not placeholder:
            raise TypeError(
                "@associate placeholder"
                + f" '{placeholder_name}'"
                + f" is not declared on {node_type.__name__}"
            )
        setattr(node_type, placeholder_name, spec.affair_type)
        claimed_by_identity.add(placeholder_name)

    claims: dict[str, type[MutableAffair]] = {}
    for _method_name, spec in associate_specs:
        if spec.expose_as is None:
            continue
        if spec.expose_as in claims:
            raise TypeError(
                f"Multiple @associate methods claim the placeholder '{spec.expose_as}'"
            )
        claims[spec.expose_as] = spec.affair_type

    for placeholder_name in placeholder_names:
        if placeholder_name in claimed_by_identity:
            continue
        generated_affair = claims.get(placeholder_name)
        if generated_affair is None:
            continue
        if generated_affair.__name__ != placeholder_name:
            _ = rename_generated_affair(generated_affair, placeholder_name)
        setattr(node_type, placeholder_name, generated_affair)


class NodeMeta(type):
    """Metaclass for :class:`Node`.

    Scans class bodies for :class:`AffairPlaceholder` instances (created by
    ``affair()``) and records them.  After the class is created, pairs each
    placeholder with its ``@associate`` handler and replaces the placeholder
    with the generated ``MutableAffair`` subclass.
    """

    _affair_placeholders: dict[str, AffairPlaceholder] = {}

    @classmethod
    @override
    def __prepare__(
        cls,
        name: str,
        bases: tuple[type[object], ...],
        **kwargs: object,
    ) -> dict[str, object]:
        return {}

    def __new__(
        cls,
        name: str,
        bases: tuple[type[object], ...],
        namespace: dict[str, object],
    ) -> NodeMeta:
        node_type = cast(NodeMeta, super().__new__(cls, name, bases, namespace))
        placeholders = {
            attr_name: value
            for attr_name, value in namespace.items()
            if isinstance(value, AffairPlaceholder)
        }
        for attr_name, placeholder in placeholders.items():
            placeholder.name = attr_name
        node_type._affair_placeholders = placeholders
        _backfill_declared_affair_placeholders(cast(type[object], node_type))
        return node_type


class Node(metaclass=NodeMeta):
    """Base class for all nodes in an affairon node tree.

    A node holds its own state, a set of mounted children, and a local
    :class:`~affairon.RuntimeRegistry` for ``provide``/``inject``.

    Nodes are composed into a tree.  The tree root is marked with ``@root``
    (class decorator) or ``mark_root()`` (instance call).  Children are either
    declared with ``inject_to(Parent)`` (auto-mounted) or attached at runtime
    with ``mount()``.  Once the tree is connected to a
    :class:`~affairon.Dispatcher` via ``attach_dispatcher()``, all
    ``@associate`` handlers are registered as dispatcher listeners.

    Handlers can also be called directly as regular methods -- they work
    both as affair-dispatched callbacks and as plain method calls.
    """

    _runtime_registry: RuntimeRegistry
    _is_root: bool
    _associate_registrations: list[tuple[object, type[MutableAffair], object]]

    def __init__(self) -> None:
        self._runtime_registry = RuntimeRegistry()
        self._mounted_children: dict[str, Node] = {}
        self._associate_registrations = []
        self._dispatcher: Dispatcher | None = None
        self._owner: object | None = None
        self._route_name: str | None = None
        self._root: Node | None = None
        self._is_root = bool(getattr(type(self), ROOT_MARK_ATTR, False))
        if self._is_root:
            self._root = self
            self._auto_mount_declared_children()

    def provide(self, runtime: _T) -> _T:
        """Store *runtime* in this node's local registry, keyed by its type.

        Other nodes can retrieve it via ``inject()`` on the same node, or
        from a different node using a Locator path expression (e.g.
        ``Annotated[Clock, Root / Clock]``).

        Returns the stored object for chaining convenience.
        """
        return self._runtime_registry.provide(runtime)

    def inject(self, key: type[_T]) -> _T:
        """Retrieve an object previously stored with ``provide()``.

        Raises :class:`LookupError` if *key* was never provided on this node.
        For cross-node lookups, use Locator path expressions on ``@associate``
        parameters instead of calling ``inject()`` directly.
        """
        return self._runtime_registry.inject(key)

    def mark_root(self) -> Self:
        """Mark this instance as a tree root (alternative to ``@root``).

        Useful when you need a plain ``Node()`` as root without defining
        a dedicated subclass::

            root = Node().mark_root()
            root.mount(SomeChild())
        """
        self._is_root = True
        self._root = self
        self._auto_mount_declared_children()
        self._bind_associated_methods()
        return self

    def attach_dispatcher(self, dispatcher: Dispatcher) -> Self:
        """Connect the entire node tree to *dispatcher*.

        Walks every node in the tree and registers each ``@associate``
        handler as a listener on the dispatcher.  After this call, emitting
        an affair through the dispatcher triggers the matching node handler.
        """
        self.root._dispatcher = dispatcher
        self.root._bind_all_associated_methods()
        return self

    def _set_mount(self, *, owner: object, route_name: str, root: Node) -> None:
        self._owner = owner
        self._route_name = route_name
        self._root = root
        self._is_root = self is root
        self._auto_mount_declared_children()
        if self.root._dispatcher is not None:
            self._bind_associated_methods()

    def _bind_all_associated_methods(self) -> None:
        self._bind_associated_methods()
        for child in self._mounted_children.values():
            child._bind_all_associated_methods()

    def _bind_associated_methods(self) -> None:
        dispatcher = self.root._dispatcher if self._root is not None else None
        if dispatcher is None:
            return

        seen: set[str] = set()
        for klass in type(self).__mro__:
            namespace = cast(Mapping[str, object], vars(klass))
            for name, attr in namespace.items():
                if name in seen:
                    continue
                inner = attr
                if isinstance(attr, (staticmethod, classmethod)):
                    inner = cast(Callable[..., object], attr.__func__)
                spec = get_associate_spec(inner)
                if spec is None:
                    continue
                bound = cast(_BoundAssociate, getattr(self, name))
                validate_listener_mode(dispatcher, bound)

                def when(affair: MutableAffair, self: Node = self) -> bool:
                    return getattr(affair, "node", None) is self

                callback = _build_associate_callback(bound)
                typed_callback = cast(SyncCallback, callback)
                dispatcher.register(spec.affair_type, typed_callback, when=when)
                self._associate_registrations.append(
                    (dispatcher, spec.affair_type, typed_callback)
                )
                seen.add(name)

    def _auto_mount_declared_children(self) -> None:
        declared = cast(list[type[Node]], getattr(type(self), AUTO_CHILDREN_ATTR, []))
        for child_type in declared:
            route_name = getattr(child_type, ROUTE_ATTR, None)
            if not isinstance(route_name, str):
                raise TypeError(f"{child_type.__name__} is missing @route")
            if route_name in self._mounted_children:
                continue
            try:
                child = child_type()
            except TypeError as exc:
                raise TypeError(
                    "Auto-mounted node"
                    + f" {child_type.__name__}"
                    + " must have a zero-arg constructor"
                ) from exc
            self._mount_child(child)

    def _mount_child(self, child: Node) -> None:
        route_name = getattr(type(child), ROUTE_ATTR, None)
        if not isinstance(route_name, str):
            raise TypeError(f"{type(child).__name__} is missing @route")
        if route_name in self._mounted_children:
            raise ValueError(
                f"Route '{route_name}' already mounted on {type(self).__name__}"
            )
        if self._root is None:
            raise ValueError(f"{type(self).__name__} is not attached to a root")
        child._set_mount(owner=self, route_name=route_name, root=self._root)
        self._mounted_children[route_name] = child
        setattr(self, route_name, child)

    def mount(self, node: Node) -> Node:
        """Mount *node* as a child of this node at runtime.

        The child's ``@route`` name determines the attribute name.  For
        declarative mounting, prefer ``inject_to()`` instead -- ``mount()``
        is for cases where the child is created dynamically::

            room = Room()                # @root, auto-mounts declared children
            room.mount(ExtraPlugin())    # add a child that wasn't declared

        Raises :class:`ValueError` if this node is not part of a tree or
        the route name is already taken.
        """
        if self._root is None:
            raise ValueError(f"{type(self).__name__} is not attached to a root")
        route_name = _require_route_name(type(node))
        if self._is_root:
            node._set_mount(
                owner=self,
                route_name=route_name,
                root=self,
            )
            self._mounted_children[route_name] = node
            setattr(self, route_name, node)
            return node
        self._mount_child(node)
        return node

    def resolve(self, locator: Locator, expected_type: type[_T]) -> _T:
        """Resolve a :class:`~affairon.Locator` path expression from this node.

        Typically you don't call this directly -- ``@associate`` handlers
        use ``Annotated[T, Root / T]`` parameter hints, and the framework
        calls ``resolve`` under the hood.
        """
        if self._root is None:
            raise ValueError(f"{type(self).__name__} is not attached to a root")
        return self._root._resolve_from(locator, expected_type, start=self)

    def _resolve_from(
        self,
        locator: Locator,
        expected_type: type[_T],
        *,
        start: Node | None,
    ) -> _T:
        target = self._resolve_object(locator, start=start)
        if not isinstance(target, expected_type):
            raise LookupError(
                f"Locator {locator!r} resolved to"
                + f" {type(target).__name__},"
                + f" expected {expected_type.__name__}"
            )
        return target

    def _resolve_object(self, locator: Locator, *, start: Node | None = None) -> object:
        if not locator.segments:
            raise LookupError("Empty locator is not allowed")

        segments = list(locator.segments)
        current: object
        first = segments.pop(0)
        if first is Root:
            current = self
        elif first is Parent:
            if start is None or start._owner is None:
                raise LookupError("Parent locator requires a mounted start node")
            current = start._owner
        else:
            raise LookupError(f"Locator must start with Root or Parent, got {first!r}")

        for segment in segments:
            if segment is Parent:
                if not isinstance(current, Node) or current._owner is None:
                    raise LookupError("Parent traversal exceeded root")
                current = current._owner
                continue
            if isinstance(segment, str):
                try:
                    current = cast(object, getattr(current, segment))
                except AttributeError as exc:
                    raise LookupError(f"Route segment '{segment}' not found") from exc
                continue
            if isinstance(segment, type):
                if isinstance(current, Node):
                    if isinstance(current, segment):
                        continue
                    try:
                        current = current.inject(cast(type[object], segment))
                        continue
                    except LookupError:
                        pass
                    route_name = getattr(segment, ROUTE_ATTR, None)
                    if (
                        isinstance(route_name, str)
                        and route_name in current._mounted_children
                    ):
                        current = current._mounted_children[route_name]
                        continue
                if isinstance(current, segment):
                    continue
                raise LookupError(
                    f"Type segment {segment.__name__}"
                    + " not found at current"
                    + " locator position"
                )
            raise LookupError(f"Unsupported locator segment: {segment!r}")
        return current

    @property
    def root(self) -> Node:
        if self._root is None:
            raise ValueError(f"{type(self).__name__} is not attached to a root")
        return self._root


def _require_route_name(node_type: type[Node]) -> str:
    route_name = getattr(node_type, ROUTE_ATTR, None)
    if not isinstance(route_name, str):
        raise TypeError(f"{node_type.__name__} is missing @route")
    return route_name


class _BoundAssociate(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


def _build_associate_callback(
    bound: _BoundAssociate,
) -> Callable[[MutableAffair], object]:
    parameters = inspect.signature(bound).parameters

    if inspect.iscoroutinefunction(bound):

        async def async_callback(affair: MutableAffair) -> object:
            kwargs = _build_associate_kwargs(parameters, affair)
            async_bound = cast(Callable[..., Awaitable[object]], bound)
            return await async_bound(**kwargs)

        return async_callback

    def sync_callback(affair: MutableAffair) -> object:
        kwargs = _build_associate_kwargs(parameters, affair)
        return bound(**kwargs)

    return sync_callback


def _build_associate_kwargs(
    parameters: Mapping[str, inspect.Parameter],
    affair: MutableAffair,
) -> dict[str, object]:
    values = affair.model_dump()
    kwargs: dict[str, object] = {}
    if "affair" in parameters:
        kwargs["affair"] = affair
    for name in parameters:
        if name in {"self", "affair"}:
            continue
        if name in values:
            kwargs[name] = values[name]
    return kwargs


__all__ = [
    "AUTO_CHILDREN_ATTR",
    "INJECT_PARENT_ATTR",
    "Node",
    "ROOT_MARK_ATTR",
    "inject_to",
    "root",
    "route",
]
