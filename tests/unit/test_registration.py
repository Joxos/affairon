"""Tests for listener registration and unregistration via Dispatcher API."""

import pytest

from eventd.dispatcher import Dispatcher
from eventd.event import Event
from eventd.exceptions import CyclicDependencyError


class TestEvent(Event):
    """Test event."""

    data: str


class TestChildEvent(TestEvent):
    """Child event for MRO testing."""

    extra: int = 0


class TestDispatcherRegistration:
    """Test Dispatcher listener registration methods."""

    def test_on_decorator_registers_listener(self):
        """on() decorator registers listener to event type."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent)
        def handler(event: Event) -> dict:
            return {"result": "test"}

        # Verify registration by checking registry
        plan = dispatcher._registry.resolve_order(TestEvent)
        assert len(plan) == 1
        assert len(plan[0]) == 1
        assert plan[0][0].callback == handler

    def test_on_decorator_returns_original_function(self):
        """on() decorator returns the original function unchanged."""
        dispatcher = Dispatcher()

        def handler(event: Event) -> dict:
            return {}

        decorated = dispatcher.on(TestEvent)(handler)
        assert decorated is handler

    def test_on_decorator_supports_multiple_event_types(self):
        """on() decorator can register to multiple event types."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent, TestChildEvent)
        def handler(event: Event) -> dict:
            return {}

        plan1 = dispatcher._registry.resolve_order(TestEvent)
        plan2 = dispatcher._registry.resolve_order(TestChildEvent)

        assert len(plan1[0]) >= 1
        assert len(plan2[0]) >= 1

    def test_on_decorator_with_priority(self):
        """on() decorator respects priority parameter."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent, priority=10)
        def high_priority(event: Event) -> dict:
            return {}

        @dispatcher.on(TestEvent, priority=1)
        def low_priority(event: Event) -> dict:
            return {}

        plan = dispatcher._registry.resolve_order(TestEvent)
        assert len(plan) == 2
        assert plan[0][0].callback == high_priority
        assert plan[1][0].callback == low_priority

    def test_on_decorator_with_after(self):
        """on() decorator respects after parameter."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent)
        def handler_a(event: Event) -> dict:
            return {}

        @dispatcher.on(TestEvent, after=[handler_a])
        def handler_b(event: Event) -> dict:
            return {}

        plan = dispatcher._registry.resolve_order(TestEvent)
        assert len(plan) == 1
        assert plan[0][0].callback == handler_a
        assert plan[0][1].callback == handler_b

    def test_on_decorator_with_unregistered_after_raises_value_error(self):
        """on() decorator raises ValueError.

        If after references unregistered callback.
        """
        dispatcher = Dispatcher()

        def unregistered(event: Event) -> dict:
            return {}

        with pytest.raises(ValueError) as exc_info:

            @dispatcher.on(TestEvent, after=[unregistered])
            def handler(event: Event) -> dict:
                return {}

        assert "unregistered" in str(exc_info.value).lower()

    def test_on_decorator_with_cyclic_after_raises_error(self):
        """on() decorator raises CyclicDependencyError if after forms cycle."""
        dispatcher = Dispatcher()

        @dispatcher.on(TestEvent)
        def handler_a(event: Event) -> dict:
            return {}

        @dispatcher.on(TestEvent, after=[handler_a])
        def handler_b(event: Event) -> dict:
            return {}

        with pytest.raises(CyclicDependencyError):

            @dispatcher.on(TestEvent, after=[handler_b])
            def handler_a_cyclic(event: Event) -> dict:
                return {}

    def test_register_method_registers_listener(self):
        """register() method registers listener to event type."""
        dispatcher = Dispatcher()

        def handler(event: Event) -> dict:
            return {}

        dispatcher.register(TestEvent, handler)

        plan = dispatcher._registry.resolve_order(TestEvent)
        assert len(plan) == 1
        assert plan[0][0].callback == handler

    def test_register_method_supports_event_type_list(self):
        """register() method accepts list of event types."""
        dispatcher = Dispatcher()

        def handler(event: Event) -> dict:
            return {}

        dispatcher.register([TestEvent, TestChildEvent], handler)

        plan1 = dispatcher._registry.resolve_order(TestEvent)
        plan2 = dispatcher._registry.resolve_order(TestChildEvent)

        assert len(plan1[0]) >= 1
        assert len(plan2[0]) >= 1

    def test_register_method_with_priority_and_after(self):
        """register() method respects priority and after parameters."""
        dispatcher = Dispatcher()

        def handler_a(event: Event) -> dict:
            return {}

        def handler_b(event: Event) -> dict:
            return {}

        dispatcher.register(TestEvent, handler_a, priority=10)
        dispatcher.register(TestEvent, handler_b, priority=5, after=[handler_a])

        plan = dispatcher._registry.resolve_order(TestEvent)
        # handler_a should be in higher priority layer
        assert plan[0][0].callback == handler_a


class TestDispatcherUnregistration:
    """Test Dispatcher listener unregistration methods."""

    def test_unregister_mode_1_specific_callback_from_specific_event(self):
        """unregister(event_types, callback) removes specific listener."""
        dispatcher = Dispatcher()

        def handler(event: Event) -> dict:
            return {}

        dispatcher.register(TestEvent, handler)
        dispatcher.unregister(TestEvent, handler)

        plan = dispatcher._registry.resolve_order(TestEvent)
        assert plan == []

    def test_unregister_mode_2_all_listeners_from_specific_event(self):
        """unregister(event_types, None) removes all listeners."""
        dispatcher = Dispatcher()

        def handler1(event: Event) -> dict:
            return {}

        def handler2(event: Event) -> dict:
            return {}

        dispatcher.register(TestEvent, handler1)
        dispatcher.register(TestEvent, handler2)
        dispatcher.unregister(TestEvent, None)

        plan = dispatcher._registry.resolve_order(TestEvent)
        assert plan == []

    def test_unregister_mode_3_callback_from_all_events(self):
        """unregister(None, callback) removes callback from all event types."""
        dispatcher = Dispatcher()

        def handler(event: Event) -> dict:
            return {}

        dispatcher.register([TestEvent, TestChildEvent], handler)
        dispatcher.unregister(None, handler)

        plan1 = dispatcher._registry.resolve_order(TestEvent)
        plan2 = dispatcher._registry.resolve_order(TestChildEvent)

        assert not any(e.callback == handler for layer in plan1 for e in layer)
        assert not any(e.callback == handler for layer in plan2 for e in layer)

    def test_unregister_mode_4_both_none_raises_value_error(self):
        """unregister(None, None) raises ValueError."""
        dispatcher = Dispatcher()

        with pytest.raises(ValueError):
            dispatcher.unregister(None, None)

    def test_unregister_unregistered_callback_raises_value_error(self):
        """unregister unregistered callback raises ValueError."""
        dispatcher = Dispatcher()

        def unregistered(event: Event) -> dict:
            return {}

        with pytest.raises(ValueError):
            dispatcher.unregister(TestEvent, unregistered)

    def test_unregister_depended_listener_raises_value_error(self):
        """unregister listener with active dependencies raises ValueError."""
        dispatcher = Dispatcher()

        def handler_a(event: Event) -> dict:
            return {}

        def handler_b(event: Event) -> dict:
            return {}

        dispatcher.register(TestEvent, handler_a)
        dispatcher.register(TestEvent, handler_b, after=[handler_a])

        with pytest.raises(ValueError) as exc_info:
            dispatcher.unregister(TestEvent, handler_a)

        assert "depend" in str(exc_info.value).lower()
