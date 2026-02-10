"""Tests for asynchronous AsyncDispatcher.emit() functionality."""

import asyncio

import pytest

from eventd.dispatcher import AsyncDispatcher
from eventd.event import Event
from eventd.exceptions import KeyConflictError


class TestEvent(Event):
    """Test event."""

    data: str


class TestChildEvent(TestEvent):
    """Child event for MRO testing."""

    extra: int = 0


class TestAsyncEmitBasics:
    """Test basic async emit functionality."""

    @pytest.mark.asyncio
    async def test_emit_injects_event_id_and_timestamp(self):
        """emit() injects event_id and timestamp into event."""
        dispatcher = AsyncDispatcher()

        event = TestEvent(data="test")
        assert event.event_id is None
        assert event.timestamp is None

        await dispatcher.emit(event)

        assert event.event_id is not None
        assert event.timestamp is not None

    @pytest.mark.asyncio
    async def test_emit_returns_empty_dict_with_no_listeners(self):
        """emit() returns empty dict when no listeners registered."""
        dispatcher = AsyncDispatcher()
        result = await dispatcher.emit(TestEvent(data="test"))
        assert result == {}

    @pytest.mark.asyncio
    async def test_emit_executes_single_listener(self):
        """emit() executes registered async listener."""
        dispatcher = AsyncDispatcher()
        executed = []

        @dispatcher.on(TestEvent)
        async def handler(event: Event) -> dict:
            executed.append(event)
            return {"result": "success"}

        event = TestEvent(data="test")
        result = await dispatcher.emit(event)

        assert len(executed) == 1
        assert result == {"result": "success"}

    @pytest.mark.asyncio
    async def test_emit_executes_multiple_listeners(self):
        """emit() executes all registered async listeners."""
        dispatcher = AsyncDispatcher()
        executed = []

        @dispatcher.on(TestEvent)
        async def handler1(event: Event) -> dict:
            executed.append(1)
            return {"key1": "value1"}

        @dispatcher.on(TestEvent)
        async def handler2(event: Event) -> dict:
            executed.append(2)
            return {"key2": "value2"}

        await dispatcher.emit(TestEvent(data="test"))

        assert 1 in executed
        assert 2 in executed

    @pytest.mark.asyncio
    async def test_emit_merges_listener_results(self):
        """emit() merges all listener return dicts."""
        dispatcher = AsyncDispatcher()

        @dispatcher.on(TestEvent)
        async def handler1(event: Event) -> dict:
            return {"key1": "value1"}

        @dispatcher.on(TestEvent)
        async def handler2(event: Event) -> dict:
            return {"key2": "value2"}

        result = await dispatcher.emit(TestEvent(data="test"))

        assert result == {"key1": "value1", "key2": "value2"}


class TestAsyncEmitParallelism:
    """Test same-priority parallelism via TaskGroup."""

    @pytest.mark.asyncio
    async def test_emit_executes_same_priority_listeners_in_parallel(self):
        """emit() executes same-priority listeners in parallel."""
        dispatcher = AsyncDispatcher()
        start_times = []

        @dispatcher.on(TestEvent, priority=0)
        async def handler1(event: Event) -> dict:
            start_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)
            return {"key1": "value1"}

        @dispatcher.on(TestEvent, priority=0)
        async def handler2(event: Event) -> dict:
            start_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)
            return {"key2": "value2"}

        await dispatcher.emit(TestEvent(data="test"))

        # Both should start within a small time window (parallel execution)
        assert len(start_times) == 2
        time_diff = abs(start_times[0] - start_times[1])
        assert time_diff < 0.05  # Started within 50ms

    @pytest.mark.asyncio
    async def test_emit_executes_different_priority_layers_sequentially(self):
        """emit() executes different priority layers sequentially."""
        dispatcher = AsyncDispatcher()
        order = []

        @dispatcher.on(TestEvent, priority=10)
        async def high_priority(event: Event) -> None:
            order.append("high_start")
            await asyncio.sleep(0.05)
            order.append("high_end")

        @dispatcher.on(TestEvent, priority=1)
        async def low_priority(event: Event) -> None:
            order.append("low")

        await dispatcher.emit(TestEvent(data="test"))

        # High priority layer must complete before low priority starts
        assert order.index("high_start") < order.index("high_end")
        assert order.index("high_end") < order.index("low")


class TestAsyncEmitErrorHandling:
    """Test error handling in async emit()."""

    @pytest.mark.asyncio
    async def test_emit_raises_type_error_if_listener_returns_non_dict(self):
        """emit() raises TypeError if listener returns non-dict."""
        dispatcher = AsyncDispatcher()

        @dispatcher.on(TestEvent)
        async def bad_handler(event: Event) -> str:
            return "not a dict"

        with pytest.raises(TypeError):
            await dispatcher.emit(TestEvent(data="test"))

    @pytest.mark.asyncio
    async def test_emit_raises_key_conflict_error_on_duplicate_keys(self):
        """emit() raises KeyConflictError if dicts have overlapping keys."""
        dispatcher = AsyncDispatcher()

        @dispatcher.on(TestEvent)
        async def handler1(event: Event) -> dict:
            return {"key": "value1"}

        @dispatcher.on(TestEvent)
        async def handler2(event: Event) -> dict:
            return {"key": "value2"}

        with pytest.raises(KeyConflictError):
            await dispatcher.emit(TestEvent(data="test"))

    @pytest.mark.asyncio
    async def test_emit_propagates_listener_exceptions(self):
        """emit() propagates exceptions from listeners."""
        dispatcher = AsyncDispatcher()

        @dispatcher.on(TestEvent)
        async def failing_handler(event: Event) -> dict:
            raise RuntimeError("Async listener error")

        with pytest.raises((RuntimeError, ExceptionGroup)):
            await dispatcher.emit(TestEvent(data="test"))

    @pytest.mark.asyncio
    async def test_emit_produces_exception_group_on_multiple_failures(self):
        """emit() produces ExceptionGroup if multiple same-priority listeners fail."""
        dispatcher = AsyncDispatcher()

        @dispatcher.on(TestEvent)
        async def handler1(event: Event) -> dict:
            raise ValueError("Error 1")

        @dispatcher.on(TestEvent)
        async def handler2(event: Event) -> dict:
            raise ValueError("Error 2")

        with pytest.raises(ExceptionGroup) as exc_info:
            await dispatcher.emit(TestEvent(data="test"))

        # ExceptionGroup should contain both errors
        assert len(exc_info.value.exceptions) == 2

    @pytest.mark.asyncio
    async def test_emit_raises_runtime_error_if_shut_down(self):
        """emit() raises RuntimeError if dispatcher is shut down."""
        dispatcher = AsyncDispatcher()
        await dispatcher.shutdown()

        with pytest.raises(RuntimeError):
            await dispatcher.emit(TestEvent(data="test"))


class TestAsyncEmitRecursion:
    """Test recursive await emit() calls."""

    @pytest.mark.asyncio
    async def test_emit_allows_recursive_calls(self):
        """emit() allows listeners to recursively await emit()."""
        dispatcher = AsyncDispatcher()
        executed = []

        @dispatcher.on(TestChildEvent)
        async def child_handler(event: Event) -> None:
            executed.append("child")

        @dispatcher.on(TestEvent)
        async def parent_handler(event: Event) -> None:
            executed.append("parent")
            if isinstance(event, TestEvent) and not isinstance(event, TestChildEvent):
                # Recursively emit a child event
                await dispatcher.emit(TestChildEvent(data="nested", extra=1))

        await dispatcher.emit(TestEvent(data="root"))

        assert "parent" in executed
        assert "child" in executed


class TestAsyncEmitCustomGenerators:
    """Test custom generators in async dispatcher."""

    @pytest.mark.asyncio
    async def test_emit_uses_custom_event_id_generator(self):
        """emit() uses custom event_id_generator if provided."""

        def custom_id_gen():
            return 7777

        dispatcher = AsyncDispatcher(event_id_generator=custom_id_gen)
        event = TestEvent(data="test")

        await dispatcher.emit(event)

        assert event.event_id == 7777

    @pytest.mark.asyncio
    async def test_emit_uses_auto_increment_event_id_by_default(self):
        """emit() auto-increments event_id by default."""
        dispatcher = AsyncDispatcher()

        event1 = TestEvent(data="first")
        event2 = TestEvent(data="second")

        await dispatcher.emit(event1)
        await dispatcher.emit(event2)

        assert event2.event_id == event1.event_id + 1
