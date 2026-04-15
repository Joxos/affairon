from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, ClassVar, cast

import pytest

from affairon import Dispatcher, Node, Parent, Root, affair, associate, route
from affairon.affairs import MutableAffair
from affairon.associate import get_associate_spec


class PhaseRuntime:
    def __init__(self, phase: str) -> None:
        self.phase = phase


@route("phase")
class PhaseNode(Node):
    CurrentAffair: ClassVar[type[MutableAffair]]

    @associate(CurrentAffair := affair())
    def current(self, runtime: PhaseRuntime) -> str:
        return runtime.phase


@route("owner")
class OwnerNode(Node):
    pass


@route("child")
class ChildNode(Node):
    ReadParentAffair: ClassVar[type[MutableAffair]]

    @associate(ReadParentAffair := affair())
    def read_parent_runtime(
        self,
        runtime: Annotated[PhaseRuntime, Parent / OwnerNode / PhaseRuntime],
    ) -> str:
        return runtime.phase


@route("duel")
class DuelNode(Node):
    LoseLifeAffair: ClassVar[type[MutableAffair]]
    SetPhaseAffair: ClassVar[type[MutableAffair]]
    GainLifeAffair: ClassVar[type[MutableAffair]]

    @associate(LoseLifeAffair := affair())
    def lose_life(self, amount: int) -> dict[str, int]:
        self.life = getattr(self, "life", 8000) - amount
        return {"life": self.life}

    @associate(SetPhaseAffair := affair())
    def set_phase(self, phase: str) -> dict[str, str]:
        self.phase_value = phase
        return {"phase": phase}

    @associate(GainLifeAffair := affair())
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
        @associate(BadAffair := affair())
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


def test_exposed_affair_name_is_backfilled_with_generated_class() -> None:
    spec = get_associate_spec(DuelNode.set_phase)

    assert spec is not None
    exposed = cast(Mapping[str, object], vars(DuelNode))["SetPhaseAffair"]
    assert exposed is spec.affair_type


def test_multiple_exposed_affairs_bind_directly() -> None:
    spec = get_associate_spec(DuelNode.lose_life)

    assert spec is not None
    exposed = cast(Mapping[str, object], vars(DuelNode))["LoseLifeAffair"]
    assert exposed is spec.affair_type


def test_walrus_bound_affair_is_exposed() -> None:
    spec = get_associate_spec(DuelNode.gain_life)

    assert spec is not None
    exposed = cast(Mapping[str, object], vars(DuelNode))["GainLifeAffair"]
    assert exposed is spec.affair_type


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


def test_walrus_affair_syntax_exec_works() -> None:
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
    @associate(SetPhaseAffair := affair())
    def set_phase(self, phase: str) -> dict[str, str]:
        self.phase_value = phase
        return {'phase': phase}
""",
        namespace,
    )

    duel_type = namespace["DuelSnippet"]
    spec = get_associate_spec(duel_type.set_phase)
    assert spec is not None
    exposed = cast(Mapping[str, object], vars(duel_type))["SetPhaseAffair"]
    assert exposed is spec.affair_type

    dispatcher = Dispatcher()
    duel = duel_type().mark_root().attach_dispatcher(dispatcher)
    result = dispatcher.emit(spec.affair_type(node=duel, phase="BATTLE"))

    assert result == {"phase": "BATTLE"}


def test_associate_requires_walrus_bound_name_for_inline_affair() -> None:
    with pytest.raises(
        TypeError, match=r"requires a walrus-bound class attribute name"
    ):

        @route("bad")
        class BadNode(Node):
            @associate(affair())
            def bad(self, amount: int) -> dict[str, int]:
                return {"amount": amount}


def test_associate_rejects_arbitrary_types() -> None:
    with pytest.raises(TypeError, match=r"expects affair\(\)"):

        @associate(object)
        def bad_method(self, x: int) -> None:
            pass


def test_associate_preserves_return_type_annotation() -> None:
    import inspect

    spec = get_associate_spec(DuelNode.set_phase)
    assert spec is not None
    sig = inspect.signature(DuelNode.set_phase)
    assert sig.return_annotation == "dict[str, str]"


def test_associate_runtime_signature_shows_user_params() -> None:
    import inspect

    sig = inspect.signature(DuelNode.set_phase)
    param_names = list(sig.parameters.keys())
    assert param_names == ["self", "phase"]
    assert sig.parameters["phase"].annotation == "str"


def test_associate_runtime_signature_strips_injected_locator_params() -> None:
    import inspect

    sig = inspect.signature(ChildNode.read_parent_runtime)
    param_names = list(sig.parameters.keys())
    assert "runtime" not in param_names
    assert param_names == ["self"]


def test_associate_bound_signature_omits_self() -> None:
    import inspect

    duel = DuelNode().mark_root()
    sig = inspect.signature(duel.set_phase)
    param_names = list(sig.parameters.keys())
    assert "self" not in param_names
    assert param_names == ["phase"]


def test_associate_local_inject_param_stripped_from_signature() -> None:
    import inspect

    sig = inspect.signature(PhaseNode.current)
    param_names = list(sig.parameters.keys())
    assert "runtime" not in param_names
    assert param_names == ["self"]
