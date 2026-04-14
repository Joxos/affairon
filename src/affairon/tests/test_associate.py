from __future__ import annotations

from typing import Annotated, cast

import pytest

from affairon import Dispatcher, Node, Parent, Root, affair, associate, route
from affairon.affairs import MutableAffair
from affairon.associate import get_associate_spec


class PhaseRuntime:
    def __init__(self, phase: str) -> None:
        self.phase = phase


@route("phase")
class PhaseNode(Node):
    CurrentAffair = affair()

    @associate(CurrentAffair)
    def current(self, runtime: PhaseRuntime) -> str:
        return runtime.phase


@route("owner")
class OwnerNode(Node):
    pass


@route("child")
class ChildNode(Node):
    ReadParentAffair = affair()

    @associate(ReadParentAffair)
    def read_parent_runtime(
        self,
        runtime: Annotated[PhaseRuntime, Parent / OwnerNode / PhaseRuntime],
    ) -> str:
        return runtime.phase


@route("duel")
class DuelNode(Node):
    SetPhaseAffair = affair()
    LoseLifeAffair = affair()

    @associate(LoseLifeAffair)
    def lose_life(self, amount: int) -> dict[str, int]:
        self.life = getattr(self, "life", 8000) - amount
        return {"life": self.life}

    @associate(SetPhaseAffair)
    def set_phase(self, phase: str) -> dict[str, str]:
        self.phase_value = phase
        return {"phase": phase}

    @associate(affair())
    def gain_life(self, amount: int) -> dict[str, int]:
        self.life = getattr(self, "life", 8000) + amount
        return {"life": self.life}


def test_associate_injects_local_runtime() -> None:
    root = Node().mark_root()
    node = root.mount(PhaseNode())
    node.provide(PhaseRuntime("DRAW"))

    current = cast(PhaseNode, node)

    assert current.current() == "DRAW"


def test_associate_resolves_annotated_locator() -> None:
    root = Node().mark_root()
    owner = root.mount(OwnerNode())
    owner.provide(PhaseRuntime("BATTLE"))
    child = ChildNode()
    owner._mount_child(child)

    assert child.read_parent_runtime() == "BATTLE"


def test_locator_leaf_type_must_match_annotation() -> None:
    root = Node().mark_root()
    owner = root.mount(OwnerNode())
    owner.provide(PhaseRuntime("BATTLE"))

    class BadNode(Node):
        BadAffair = affair()

        @associate(BadAffair)
        def bad(
            self,
            runtime: Annotated[PhaseRuntime, Root / OwnerNode / OwnerNode],
        ) -> str:
            return runtime.phase

    bad = BadNode()
    bad._set_mount(owner=owner, route_name="bad", root=root)

    with pytest.raises(
        TypeError, match="Locator leaf must match annotated runtime type"
    ):
        bad.bad()


def test_associate_generates_affair_class() -> None:
    spec = get_associate_spec(DuelNode.set_phase)

    assert spec is not None
    assert issubclass(spec.affair_type, MutableAffair)
    affair_instance = spec.affair_type(node=object(), phase="DRAW")
    assert affair_instance.model_dump()["phase"] == "DRAW"


def test_declared_affair_placeholder_is_backfilled_with_generated_class() -> None:
    spec = get_associate_spec(DuelNode.set_phase)

    assert spec is not None
    assert DuelNode.SetPhaseAffair is spec.affair_type


def test_declared_placeholders_bind_directly() -> None:
    spec = get_associate_spec(DuelNode.lose_life)

    assert spec is not None
    assert DuelNode.LoseLifeAffair is spec.affair_type


def test_anonymous_placeholder_is_not_exposed() -> None:
    spec = get_associate_spec(DuelNode.gain_life)

    assert spec is not None
    # The affair() passed inline has no name from a class attribute,
    # so it should not be exposed as a class attribute on DuelNode.
    assert not hasattr(DuelNode, "GainLifeAffair")


def test_associate_binds_generated_affair_to_dispatcher() -> None:
    dispatcher = Dispatcher()
    duel = DuelNode().mark_root().attach_dispatcher(dispatcher)

    spec = get_associate_spec(type(duel).set_phase)
    assert spec is not None

    result = dispatcher.emit(spec.affair_type(node=duel, phase="BATTLE"))

    assert result == {"phase": "BATTLE"}
    assert duel.phase_value == "BATTLE"


def test_direct_associate_call_does_not_emit() -> None:
    dispatcher = Dispatcher()
    duel = DuelNode().mark_root().attach_dispatcher(dispatcher)

    assert duel.set_phase("DRAW") == {"phase": "DRAW"}
    assert duel.phase_value == "DRAW"


def test_direct_placeholder_syntax_exec_works() -> None:
    namespace = {
        "Dispatcher": Dispatcher,
        "Node": Node,
        "affair": affair,
        "associate": associate,
        "route": route,
    }

    exec(
        """
@route('duel')
class DuelSnippet(Node):
    SetPhaseAffair = affair()

    @associate(SetPhaseAffair)
    def set_phase(self, phase: str) -> dict[str, str]:
        self.phase_value = phase
        return {'phase': phase}
""",
        namespace,
    )

    duel_type = namespace["DuelSnippet"]
    spec = get_associate_spec(duel_type.set_phase)
    assert spec is not None
    assert duel_type.SetPhaseAffair is spec.affair_type

    dispatcher = Dispatcher()
    duel = duel_type().mark_root().attach_dispatcher(dispatcher)
    result = dispatcher.emit(spec.affair_type(node=duel, phase="BATTLE"))

    assert result == {"phase": "BATTLE"}


def test_associate_rejects_arbitrary_types() -> None:
    with pytest.raises(TypeError, match="expects an affair\\(\\) placeholder"):

        @associate(object)
        def bad_method(self, x: int) -> None:
            pass
