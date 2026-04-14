from __future__ import annotations

import pytest

from affairon import Node, child_of, root, route


class PhaseRuntime:
    def __init__(self, phase: str) -> None:
        self.phase = phase


@route("phase")
class PhaseNode(Node):
    pass


@root
@route("duel")
class DuelNode(Node):
    pass


@route("child")
@child_of(DuelNode)
class ChildNode(Node):
    pass


@root
@route("broken")
class BrokenRootNode(Node):
    pass


@route("invalid")
@child_of(BrokenRootNode)
class InvalidChildNode(Node):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


def test_root_mounts_node_by_route_name() -> None:
    root_node = Node().mark_root()
    node = PhaseNode()

    root_node.mount(node)

    assert root_node._mounted_children["phase"] is node


def test_node_local_runtime_registry_still_works() -> None:
    root_node = Node().mark_root()
    node = root_node.mount(PhaseNode())

    runtime = node.provide(PhaseRuntime("DRAW"))

    assert node.inject(PhaseRuntime) is runtime


def test_marked_root_node_auto_mounts_declared_children() -> None:
    duel = DuelNode()

    assert duel.root is duel
    assert duel._mounted_children["child"].root is duel


def test_unattached_node_resolve_still_fails_fast() -> None:
    node = PhaseNode()

    with pytest.raises(ValueError, match="is not attached to a root"):
        node.resolve(object(), PhaseRuntime)  # type: ignore[arg-type]


def test_auto_mount_requires_zero_arg_constructor() -> None:
    with pytest.raises(TypeError, match="zero-arg constructor"):
        BrokenRootNode()
