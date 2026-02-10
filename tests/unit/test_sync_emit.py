"""Tests for synchronous Dispatcher.emit() functionality."""

import pytest

from eventd.dispatcher import Dispatcher
from eventd.event import Event
from eventd.exceptions import KeyConflictError


class TestEvent(Event):
    """Test event."""

    data: str


class TestChildEvent(TestEvent):
    """Child event for MRO testing."""

    extra: int = 0


class TestSyncEmitBasics:
    """Test basic emit functionality."""

    def test_emit_injects_event_id_and_timestamp(self):
        """emit() injects event_id and timestamp into event."""
        dispatcher = Dispatcher()

        event = TestEvent(data="test")
        assert event.event_id is None
        assert event.timestamp is None

        dispatcher.emit(event)

        assert event.event_id is not None
        assert event.timestamp is not None
        assert isinstance(event.event_id, int)
        assert isinstance(event.timestamp, float)

    def test_emit_returns_empty_dict_with_no_listeners(self):
        """emit() returns empty dict when no listeners registered."""
        dispatcher = Dispatcher()
        event = TestEvent(data="test")

        result = dispatcher.emit(event)

        assert result == {}

    def test_emit_executes_single_listener(self):
        """emit() executes registered listener."""
        dispatcher = Dispatcher()
        executed = []

        @dispatcher.on(TestEvent)
        def handler(event: Event) -> dict:
            executed.append(event)
            return {"result": "success"}

        event = TestEvent(data="test")
        result = dispatcher.emit(event)

        assert len(executed) == 1
        assert executed[0] == event
        assert result == {"result": "success"}

    def test_emit_executes_multiple_listeners(self):
        """emit() executes all registered listeners."""
        dispatcher = Dispatcher()
        executed = []

        @dispatcher.on(TestEvent)
        def handler1(event: Event) -> dict:
            executed.append(1)
            return {"key1": "value1"}

        @dispatcher.on(TestEvent)
        def handler2(event: Event) -> dict:
            executed.append(2)
            return {"key2": "value2"}

        dispatcher.emit(TestEvent(data="test"))

        assert executed == [1, 2]

    def test_emit_merges_listener_results(self):
        """emit() merges all listener return dicts."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent)
        def handler1(event: Event) -> dict:
            return {"key1": "value1"}

        @dispatcher.on(TestEvent)
        def handler2(event: Event) -> dict:
            return {"key2": "value2"}

        result = dispatcher.emit(TestEvent(data="test"))

        assert result == {"key1": "value1", "key2": "value2"}

    def test_emit_ignores_none_return_values(self):
        """emit() ignores listeners that return None."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent)
        def handler1(event: Event) -> dict:
            return {"key1": "value1"}

        @dispatcher.on(TestEvent)
        def handler2(event: Event) -> None:
            return None

        @dispatcher.on(TestEvent)
        def handler3(event: Event) -> dict:
            return {"key3": "value3"}

        result = dispatcher.emit(TestEvent(data="test"))

        assert result == {"key1": "value1", "key3": "value3"}


class TestSyncEmitExecutionOrder:
    """Test listener execution order."""

    def test_emit_respects_priority_order(self):
        """emit() executes listeners in priority order (high to low)."""
        dispatcher = Dispatcher()
        order = []

        @dispatcher.on(TestEvent, priority=1)
        def low_priority(event: Event) -> None:
            order.append("low")

        @dispatcher.on(TestEvent, priority=10)
        def high_priority(event: Event) -> None:
            order.append("high")

        @dispatcher.on(TestEvent, priority=5)
        def mid_priority(event: Event) -> None:
            order.append("mid")

        dispatcher.emit(TestEvent(data="test"))

        assert order == ["high", "mid", "low"]

    def test_emit_respects_after_dependencies(self):
        """emit() respects after dependencies within same priority."""
        dispatcher = Dispatcher()
        order = []

        @dispatcher.on(TestEvent)
        def handler_a(event: Event) -> None:
            order.append("a")

        @dispatcher.on(TestEvent, after=[handler_a])
        def handler_b(event: Event) -> None:
            order.append("b")

        dispatcher.emit(TestEvent(data="test"))

        assert order == ["a", "b"]

    def test_emit_respects_mro_expansion(self):
        """emit() includes listeners from parent event types via MRO."""
        dispatcher = Dispatcher()
        executed = []

        @dispatcher.on(TestEvent)
        def parent_handler(event: Event) -> None:
            executed.append("parent")

        @dispatcher.on(TestChildEvent)
        def child_handler(event: Event) -> None:
            executed.append("child")

        dispatcher.emit(TestChildEvent(data="test", extra=42))

        assert "parent" in executed
        assert "child" in executed


class TestSyncEmitErrorHandling:
    """Test error handling in emit()."""

    def test_emit_raises_type_error_if_listener_returns_non_dict(self):
        """emit() raises TypeError if listener returns non-dict."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent)
        def bad_handler(event: Event) -> str:  # Wrong return type
            return "not a dict"

        with pytest.raises(TypeError) as exc_info:
            dispatcher.emit(TestEvent(data="test"))

        assert (
            "non-dict" in str(exc_info.value).lower()
            or "dict" in str(exc_info.value).lower()
        )

    def test_emit_raises_key_conflict_error_on_duplicate_keys(self):
        """emit() raises KeyConflictError if dicts have overlapping keys."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent)
        def handler1(event: Event) -> dict:
            return {"key": "value1"}

        @dispatcher.on(TestEvent)
        def handler2(event: Event) -> dict:
            return {"key": "value2"}

        with pytest.raises(KeyConflictError):
            dispatcher.emit(TestEvent(data="test"))

    def test_emit_propagates_listener_exceptions(self):
        """emit() propagates exceptions raised by listeners."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent)
        def failing_handler(event: Event) -> dict:
            raise RuntimeError("Listener error")

        with pytest.raises(RuntimeError) as exc_info:
            dispatcher.emit(TestEvent(data="test"))

        assert "Listener error" in str(exc_info.value)

    def test_emit_raises_runtime_error_if_shut_down(self):
        """emit() raises RuntimeError if dispatcher is shut down."""
        dispatcher = Dispatcher()
        dispatcher.shutdown()

        with pytest.raises(RuntimeError) as exc_info:
            dispatcher.emit(TestEvent(data="test"))

        assert (
            "shut" in str(exc_info.value).lower()
            or "closed" in str(exc_info.value).lower()
        )


class TestSyncEmitRecursion:
    """Test recursive emit() calls."""

    def test_emit_allows_recursive_calls(self):
        """emit() allows listeners to recursively call emit()."""
        dispatcher = Dispatcher()
        executed = []

        @dispatcher.on(TestChildEvent)
        def child_handler(event: Event) -> None:
            executed.append("child")

        @dispatcher.on(TestEvent)
        def parent_handler(event: Event) -> None:
            executed.append("parent")
            if isinstance(event, TestEvent) and not isinstance(event, TestChildEvent):
                # Recursively emit a child event
                dispatcher.emit(TestChildEvent(data="nested", extra=1))

        event = TestEvent(data="root")
        dispatcher.emit(event)

        assert "parent" in executed
        assert "child" in executed


class TestSyncEmitCustomGenerators:
    """Test custom event_id and timestamp generators."""

    def test_emit_uses_custom_event_id_generator(self):
        """emit() uses custom event_id_generator if provided."""

        def custom_id_gen():
            return 9999

        dispatcher = Dispatcher(event_id_generator=custom_id_gen)
        event = TestEvent(data="test")

        dispatcher.emit(event)

        assert event.event_id == 9999

    def test_emit_uses_custom_timestamp_generator(self):
        """emit() uses custom timestamp_generator if provided."""

        def custom_ts_gen():
            return 123.456

        dispatcher = Dispatcher(timestamp_generator=custom_ts_gen)
        event = TestEvent(data="test")

        dispatcher.emit(event)

        assert event.timestamp == 123.456

    def test_emit_uses_auto_increment_event_id_by_default(self):
        """emit() auto-increments event_id by default."""
        dispatcher = Dispatcher()

        event1 = TestEvent(data="first")
        event2 = TestEvent(data="second")

        dispatcher.emit(event1)
        dispatcher.emit(event2)

        assert event2.event_id == event1.event_id + 1
