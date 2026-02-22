"""Tests for synchronous Dispatcher."""

import pytest
from conftest import ChildAffair, GrandchildAffair, ParentAffair, Ping

from affairon import Dispatcher, KeyConflictError, MutableAffair


class TestSyncDispatcher:
    def test_emit_single_listener(self):
        """Single listener returns dict via emit."""
        d = Dispatcher()
        d.register(Ping, lambda e: {"ok": True})
        assert d.emit(Ping(msg="x")) == {"ok": True}

    def test_emit_key_conflict(self):
        """Overlapping keys raise KeyConflictError."""
        d = Dispatcher()
        d.register(Ping, lambda e: {"k": 1})
        d.register(Ping, lambda e: {"k": 2})
        with pytest.raises(KeyConflictError):
            d.emit(Ping(msg="x"))

    def test_on_decorator_end_to_end(self):
        """@on() registers plain function and emit invokes it."""
        d = Dispatcher()
        called = []

        @d.on(Ping)
        def handler(e: MutableAffair) -> None:
            called.append(e)

        d.emit(Ping(msg="hi"))
        assert len(called) == 1


class TestEmitUp:
    def test_emit_up_false_fires_only_child(self):
        """Default emit_up=False only fires callbacks on the concrete type."""
        d = Dispatcher()
        parent_called = []
        child_called = []

        d.register(ParentAffair, lambda e: parent_called.append(1))
        d.register(ChildAffair, lambda e: child_called.append(1))

        d.emit(ChildAffair(msg="hi", extra="x"))

        assert child_called == [1]
        assert parent_called == []

    def test_emit_up_true_fires_child_and_parent(self):
        """emit_up=True fires child callbacks then parent callbacks."""
        d = Dispatcher()
        order = []

        d.register(ParentAffair, lambda e: order.append("parent"))
        d.register(ChildAffair, lambda e: order.append("child"))

        d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert order == ["child", "parent"]

    def test_emit_up_true_merges_results_across_hierarchy(self):
        """emit_up=True merges results from child and parent callbacks."""
        d = Dispatcher()

        d.register(ParentAffair, lambda e: {"from_parent": True})
        d.register(ChildAffair, lambda e: {"from_child": True})

        result = d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert result == {"from_child": True, "from_parent": True}

    def test_emit_up_multilevel_hierarchy(self):
        """emit_up=True walks full MRO: grandchild -> child -> parent."""
        d = Dispatcher()
        order = []

        d.register(ParentAffair, lambda e: order.append("parent"))
        d.register(ChildAffair, lambda e: order.append("child"))
        d.register(GrandchildAffair, lambda e: order.append("grandchild"))

        d.emit(GrandchildAffair(msg="hi", extra="x", detail="d", emit_up=True))

        assert order == ["grandchild", "child", "parent"]

    def test_emit_up_key_conflict_across_hierarchy(self):
        """emit_up=True raises KeyConflictError on cross-hierarchy key clash."""
        d = Dispatcher()

        d.register(ParentAffair, lambda e: {"k": "parent"})
        d.register(ChildAffair, lambda e: {"k": "child"})

        with pytest.raises(KeyConflictError):
            d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

    def test_emit_up_no_parent_listeners(self):
        """emit_up=True with no parent callbacks is a harmless no-op."""
        d = Dispatcher()

        d.register(ChildAffair, lambda e: {"from_child": True})

        result = d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert result == {"from_child": True}


class TestWhenFilter:
    def test_when_true_fires_callback(self):
        """Callback with when predicate returning True fires normally."""
        d = Dispatcher()

        @d.on(Ping, when=lambda a: a.msg == "yes")
        def handler(affair: Ping) -> dict[str, str]:
            return {"fired": affair.msg}

        result = d.emit(Ping(msg="yes"))
        assert result == {"fired": "yes"}

    def test_when_false_skips_callback(self):
        """Callback with when predicate returning False is skipped."""
        d = Dispatcher()

        @d.on(Ping, when=lambda a: a.msg == "yes")
        def handler(affair: Ping) -> dict[str, str]:
            return {"fired": affair.msg}

        result = d.emit(Ping(msg="no"))
        assert result == {}

    def test_when_none_always_fires(self):
        """Callback with when=None (default) fires unconditionally."""
        d = Dispatcher()

        @d.on(Ping)
        def handler(affair: Ping) -> dict[str, str]:
            return {"ok": "yes"}

        assert d.emit(Ping(msg="anything")) == {"ok": "yes"}

    def test_when_mixed_filtered_and_unfiltered(self):
        """Only callbacks whose when predicate passes contribute results."""
        d = Dispatcher()

        @d.on(Ping, when=lambda a: a.msg == "target")
        def selective(affair: Ping) -> dict[str, str]:
            return {"selective": "yes"}

        @d.on(Ping)
        def always(affair: Ping) -> dict[str, str]:
            return {"always": "yes"}

        result = d.emit(Ping(msg="target"))
        assert result == {"selective": "yes", "always": "yes"}

        result = d.emit(Ping(msg="other"))
        assert result == {"always": "yes"}

    def test_when_via_register(self):
        """when parameter works through register() method call."""
        d = Dispatcher()
        d.register(Ping, lambda e: {"v": 1}, when=lambda a: a.msg == "go")

        assert d.emit(Ping(msg="go")) == {"v": 1}
        assert d.emit(Ping(msg="stop")) == {}

    def test_when_with_emit_up(self):
        """when predicate is checked per-affair-type during emit_up walk."""
        d = Dispatcher()

        d.register(
            ParentAffair,
            lambda e: {"parent": True},
            when=lambda a: a.msg == "yes",
        )
        d.register(ChildAffair, lambda e: {"child": True})

        # Parent predicate passes
        result = d.emit(ChildAffair(msg="yes", extra="x", emit_up=True))
        assert result == {"child": True, "parent": True}

        # Parent predicate fails — only child fires
        result = d.emit(ChildAffair(msg="no", extra="x", emit_up=True))
        assert result == {"child": True}

    def test_when_after_ordering_preserved(self):
        """Filtered callbacks still respect after ordering for remaining ones."""
        d = Dispatcher()
        order: list[str] = []

        @d.on(Ping)
        def first(affair: Ping) -> None:
            order.append("first")

        @d.on(Ping, after=[first], when=lambda a: a.msg == "all")
        def second(affair: Ping) -> None:
            order.append("second")

        @d.on(Ping, after=[first])
        def third(affair: Ping) -> None:
            order.append("third")

        d.emit(Ping(msg="all"))
        assert "first" in order
        assert order.index("first") < order.index("second")
        assert order.index("first") < order.index("third")

        order.clear()
        d.emit(Ping(msg="partial"))
        assert "second" not in order
        assert "first" in order
        assert "third" in order
