"""Tests for AsyncDispatcher."""

import pytest
from conftest import ChildAffair, GrandchildAffair, ParentAffair, Ping

from affairon import KeyConflictError, MutableAffair
from affairon.async_dispatcher import AsyncDispatcher


class TestAsyncDispatcher:
    @pytest.mark.asyncio
    async def test_emit_merges_results(self):
        """Multiple async listeners, results merged."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"a": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"b": 2}

        result = await d.emit(Ping(msg="x"))
        assert result == {"a": 1, "b": 2}

    @pytest.mark.asyncio
    async def test_emit_exception_group(self):
        """Failing listeners propagate ExceptionGroup."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def bad1(e: MutableAffair) -> dict:
            raise ValueError("e1")

        @d.on(Ping)
        async def bad2(e: MutableAffair) -> dict:
            raise ValueError("e2")

        with pytest.raises(ExceptionGroup) as exc_info:
            await d.emit(Ping(msg="x"))
        assert len(exc_info.value.exceptions) == 2


class TestAsyncEmitUp:
    @pytest.mark.asyncio
    async def test_emit_up_false_fires_only_child(self):
        """Default emit_up=False only fires callbacks on the concrete type."""
        d = AsyncDispatcher()
        parent_called = []
        child_called = []

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> None:
            parent_called.append(1)

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> None:
            child_called.append(1)

        await d.emit(ChildAffair(msg="hi", extra="x"))

        assert child_called == [1]
        assert parent_called == []

    @pytest.mark.asyncio
    async def test_emit_up_true_fires_child_and_parent(self):
        """emit_up=True fires child callbacks then parent callbacks."""
        d = AsyncDispatcher()
        order = []

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> None:
            order.append("parent")

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> None:
            order.append("child")

        await d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert order == ["child", "parent"]

    @pytest.mark.asyncio
    async def test_emit_up_true_merges_results_across_hierarchy(self):
        """emit_up=True merges results from child and parent callbacks."""
        d = AsyncDispatcher()

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> dict:
            return {"from_parent": True}

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> dict:
            return {"from_child": True}

        result = await d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert result == {"from_child": True, "from_parent": True}

    @pytest.mark.asyncio
    async def test_emit_up_multilevel_hierarchy(self):
        """emit_up=True walks full MRO: grandchild -> child -> parent."""
        d = AsyncDispatcher()
        order = []

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> None:
            order.append("parent")

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> None:
            order.append("child")

        @d.on(GrandchildAffair)
        async def grandchild_handler(e: MutableAffair) -> None:
            order.append("grandchild")

        await d.emit(GrandchildAffair(msg="hi", extra="x", detail="d", emit_up=True))

        assert order == ["grandchild", "child", "parent"]

    @pytest.mark.asyncio
    async def test_emit_up_key_conflict_across_hierarchy(self):
        """emit_up=True raises KeyConflictError on cross-hierarchy key clash."""
        d = AsyncDispatcher()

        @d.on(ParentAffair)
        async def parent_handler(e: MutableAffair) -> dict:
            return {"k": "parent"}

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> dict:
            return {"k": "child"}

        with pytest.raises(KeyConflictError):
            await d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

    @pytest.mark.asyncio
    async def test_emit_up_no_parent_listeners(self):
        """emit_up=True with no parent callbacks is a harmless no-op."""
        d = AsyncDispatcher()

        @d.on(ChildAffair)
        async def child_handler(e: MutableAffair) -> dict:
            return {"from_child": True}

        result = await d.emit(ChildAffair(msg="hi", extra="x", emit_up=True))

        assert result == {"from_child": True}
