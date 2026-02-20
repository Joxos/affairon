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
