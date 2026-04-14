from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any, TypeVar, get_type_hints

from affairon.affairs import Affair
from affairon.associate import (
    AffairPlaceholder,
    _rename_generated_affair,
    get_associate_spec,
    iter_associate_specs,
)
from affairon.aware import _validate_listener_mode
from affairon.locator import Locator, Parent, Root
from affairon.runtime import RuntimeRegistry

_T = TypeVar("_T")
ROUTE_ATTR = "_affair_route_name"
INJECT_PARENT_ATTR = "_affair_inject_parent"
ROOT_MARK_ATTR = "_affair_root_marked"
AUTO_CHILDREN_ATTR = "_affair_auto_children"


def _is_affair_placeholder_annotation(annotation: Any) -> bool:
    return annotation is Affair or annotation == "Affair"


def route(name: str):
    def decorator(obj: Any) -> Any:
        setattr(obj, ROUTE_ATTR, name)
        return obj

    return decorator


def root(node_type: type[Node]) -> type[Node]:
    setattr(node_type, ROOT_MARK_ATTR, True)
    return node_type


def _backfill_declared_affair_placeholders(node_type: type[Any]) -> None:
    placeholders = getattr(node_type, "_affair_placeholders", {})
    placeholder_names = list(placeholders)
    if not placeholder_names:
        annotations = get_type_hints(node_type, include_extras=True)
        placeholder_names = [
            field_name
            for field_name, annotation in annotations.items()
            if annotation is Affair
        ]
    associate_specs = iter_associate_specs(node_type)
    if not placeholder_names:
        return

    claimed_by_identity: set[str] = set()
    for _method_name, spec in associate_specs:
        placeholder = spec.placeholder
        if placeholder is None:
            continue
        placeholder_name = placeholder.name
        expected = placeholders.get(placeholder_name)
        if expected is None:
            continue
        if expected is not placeholder:
            raise TypeError(
                "@associate placeholder "
                f"'{placeholder_name}' is not declared on {node_type.__name__}"
            )
        setattr(node_type, placeholder_name, spec.affair_type)
        claimed_by_identity.add(placeholder_name)

    claims: dict[str, type[Any]] = {}
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
            _rename_generated_affair(generated_affair, placeholder_name)
        setattr(node_type, placeholder_name, generated_affair)


class _NodeNamespace(dict[str, Any]):
    def __init__(self) -> None:
        super().__init__()
        self._affair_placeholders: dict[str, AffairPlaceholder] = {}

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        if key == "__annotations__" and isinstance(value, dict):
            for name, annotation in value.items():
                if (
                    _is_affair_placeholder_annotation(annotation)
                    and name not in self._affair_placeholders
                ):
                    placeholder = AffairPlaceholder(name)
                    self._affair_placeholders[name] = placeholder
                    super().__setitem__(name, placeholder)

    def __getitem__(self, key: str) -> Any:
        if key in self:
            return super().__getitem__(key)

        annotations = super().get("__annotations__", {})
        if _is_affair_placeholder_annotation(annotations.get(key)):
            placeholder = self._affair_placeholders.get(key)
            if placeholder is None:
                placeholder = AffairPlaceholder(key)
                self._affair_placeholders[key] = placeholder
            return placeholder
        raise KeyError(key)


class _NodeInjectionDescriptor:
    def __init__(self, parent_type: type[Any]) -> None:
        self.parent_type = parent_type

    def __call__(self, node_type: type[Node]) -> type[Node]:
        setattr(node_type, INJECT_PARENT_ATTR, self.parent_type)
        children = getattr(self.parent_type, AUTO_CHILDREN_ATTR, None)
        if children is None:
            children = []
            setattr(self.parent_type, AUTO_CHILDREN_ATTR, children)
        children.append(node_type)
        return node_type


class NodeMeta(type):
    _affair_placeholders: dict[str, AffairPlaceholder]

    @classmethod
    def __prepare__(
        cls,
        name: str,
        bases: tuple[type[Any], ...],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return _NodeNamespace()

    def __new__(
        cls,
        name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
    ) -> NodeMeta:
        node_type = super().__new__(cls, name, bases, namespace)
        if isinstance(namespace, _NodeNamespace):
            node_type._affair_placeholders = namespace._affair_placeholders
        _backfill_declared_affair_placeholders(node_type)
        return node_type

    @property
    def inject(cls) -> _NodeInjectionDescriptor:
        return _NodeInjectionDescriptor(cls)


class Node(metaclass=NodeMeta):
    def __init__(self) -> None:
        self._runtime_registry = RuntimeRegistry()
        self._mounted_children: dict[str, Node] = {}
        self._associate_registrations: list[tuple[Any, type[Any], Any]] = []
        self._dispatcher: Any | None = None
        self._owner: object | None = None
        self._route_name: str | None = None
        self._root: Node | None = None
        self._is_root = bool(getattr(type(self), ROOT_MARK_ATTR, False))
        if self._is_root:
            self._root = self
            self._auto_mount_declared_children()

    def provide(self, runtime: _T) -> _T:
        return self._runtime_registry.provide(runtime)

    def inject(self, key: type[_T]) -> _T:
        return self._runtime_registry.inject(key)

    def mark_root(self) -> Node:
        self._is_root = True
        self._root = self
        self._auto_mount_declared_children()
        self._bind_associated_methods()
        return self

    def attach_dispatcher(self, dispatcher: Any) -> Node:
        self.root._dispatcher = dispatcher
        self.root._bind_associated_methods()
        return self

    def _set_mount(self, *, owner: object, route_name: str, root: Node) -> None:
        self._owner = owner
        self._route_name = route_name
        self._root = root
        self._is_root = self is root
        self._auto_mount_declared_children()
        self._bind_associated_methods()

    def _bind_associated_methods(self) -> None:
        dispatcher = self.root._dispatcher if self._root is not None else None
        if dispatcher is None or not hasattr(dispatcher, "register"):
            return

        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, attr in vars(klass).items():
                if name in seen:
                    continue
                inner = attr
                if isinstance(attr, (staticmethod, classmethod)):
                    inner = attr.__func__
                spec = get_associate_spec(inner)
                if spec is None:
                    continue
                bound = getattr(self, name)
                _validate_listener_mode(dispatcher, bound)

                def when(affair: Any, self: Node = self) -> bool:
                    return getattr(affair, "node", None) is self

                callback = _build_associate_callback(bound)
                dispatcher.register(spec.affair_type, callback, when=when)
                self._associate_registrations.append(
                    (dispatcher, spec.affair_type, callback)
                )
                seen.add(name)

    def _auto_mount_declared_children(self) -> None:
        declared = getattr(type(self), AUTO_CHILDREN_ATTR, [])
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
                    "Auto-mounted node "
                    f"{child_type.__name__} must have a zero-arg constructor"
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
                f"Locator {locator!r} resolved to {type(target).__name__}, "
                f"expected {expected_type.__name__}"
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
                    current = getattr(current, segment)
                except AttributeError as exc:
                    raise LookupError(f"Route segment '{segment}' not found") from exc
                continue
            if isinstance(segment, type):
                if isinstance(current, Node):
                    if isinstance(current, segment):
                        continue
                    try:
                        current = current.inject(segment)
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
                    "Type segment "
                    f"{segment.__name__} not found at current locator position"
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


def _build_associate_callback(bound: Any) -> Any:
    parameters = inspect.signature(bound).parameters

    if inspect.iscoroutinefunction(bound):

        async def async_callback(affair: Any) -> Any:
            kwargs = _build_associate_kwargs(parameters, affair)
            return await bound(**kwargs)

        return async_callback

    def sync_callback(affair: Any) -> Any:
        kwargs = _build_associate_kwargs(parameters, affair)
        return bound(**kwargs)

    return sync_callback


def _build_associate_kwargs(
    parameters: Mapping[str, inspect.Parameter],
    affair: Any,
) -> dict[str, Any]:
    values = affair.model_dump()
    kwargs: dict[str, Any] = {}
    if "affair" in parameters:
        kwargs["affair"] = affair
    for name in parameters:
        if name in {"self", "affair"}:
            continue
        if name in values:
            kwargs[name] = values[name]
    return kwargs


class RootNode(Node):
    def __init__(self) -> None:
        super().__init__()
        self.mark_root()


__all__ = [
    "AUTO_CHILDREN_ATTR",
    "INJECT_PARENT_ATTR",
    "Node",
    "ROOT_MARK_ATTR",
    "RootNode",
    "root",
    "route",
]
