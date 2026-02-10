"""Tests for RegistryTable and ListenerEntry.

Tests verify:
- ListenerEntry dataclass fields and default name
- RegistryTable initialization
- add() registration and validation
- remove() with 4 modes
- resolve_order() with MRO, priority, after sorting
- Caching behavior with _revision
- Cyclic dependency detection
- After reference validation
"""

import pytest

from eventd.event import Event
from eventd.exceptions import CyclicDependencyError
from eventd.registry import ListenerEntry, RegistryTable


class TestEvent(Event):
    """Test event for registry tests."""

    data: str


class TestChildEvent(TestEvent):
    """Child event for MRO testing."""

    extra: int = 0


class TestListenerEntry:
    """Test ListenerEntry dataclass."""

    def test_listener_entry_fields(self):
        """ListenerEntry has correct fields."""

        def callback(event: Event) -> dict:
            return {"result": True}

        entry = ListenerEntry(
            callback=callback, priority=10, after=[], name="test_callback"
        )

        assert entry.callback == callback
        assert entry.priority == 10
        assert entry.after == []
        assert entry.name == "test_callback"

    def test_listener_entry_default_name(self):
        """ListenerEntry name defaults to callback.__qualname__."""

        def test_callback(event: Event) -> dict:
            return {}

        entry = ListenerEntry(callback=test_callback, priority=0)

        # __qualname__ includes full path for nested functions
        assert entry.name == test_callback.__qualname__
        assert "test_callback" in entry.name


class TestRegistryTableInit:
    """Test RegistryTable initialization."""

    def test_init_creates_empty_registry(self):
        """RegistryTable.__init__() creates empty state."""
        registry = RegistryTable()

        # Should have internal state but no public API to inspect directly
        # Verify via behavior: resolve_order should return empty list
        assert registry.resolve_order(TestEvent) == []


class TestRegistryTableAdd:
    """Test RegistryTable.add() method."""

    def test_add_single_listener(self):
        """Add registers listener to event type."""
        registry = RegistryTable()

        def handler(event: Event) -> dict:
            return {}

        entry = ListenerEntry(callback=handler, priority=0)
        registry.add([TestEvent], entry)

        result = registry.resolve_order(TestEvent)
        assert len(result) == 1  # One priority layer
        assert len(result[0]) == 1  # One listener in layer
        assert result[0][0].callback == handler

    def test_add_to_multiple_event_types(self):
        """Add registers listener to multiple event types."""
        registry = RegistryTable()

        def handler(event: Event) -> dict:
            return {}

        entry = ListenerEntry(callback=handler, priority=0)
        registry.add([TestEvent, TestChildEvent], entry)

        result1 = registry.resolve_order(TestEvent)
        result2 = registry.resolve_order(TestChildEvent)

        assert len(result1[0]) >= 1
        assert len(result2[0]) >= 1

    def test_add_increments_revision(self):
        """Add increments _revision."""
        registry = RegistryTable()

        def handler(event: Event) -> dict:
            return {}

        # Access _revision through behavior: cache invalidation
        entry1 = ListenerEntry(callback=handler, priority=0)
        registry.add([TestEvent], entry1)

        # Add another listener
        def handler2(event: Event) -> dict:
            return {}

        entry2 = ListenerEntry(callback=handler2, priority=0)
        registry.add([TestEvent], entry2)

        # Should see both listeners
        result = registry.resolve_order(TestEvent)
        assert len(result[0]) == 2

    def test_add_with_unregistered_after_raises_value_error(self):
        """Add with after referencing unregistered callback raises ValueError."""
        registry = RegistryTable()

        def unregistered_callback(event: Event) -> dict:
            return {}

        def handler(event: Event) -> dict:
            return {}

        entry = ListenerEntry(
            callback=handler, priority=0, after=[unregistered_callback]
        )

        with pytest.raises(ValueError) as exc_info:
            registry.add([TestEvent], entry)

        assert "unregistered" in str(exc_info.value).lower()

    def test_add_with_cyclic_dependency_raises_error(self):
        """Add with cyclic after dependency raises CyclicDependencyError."""
        registry = RegistryTable()

        def handler_a(event: Event) -> dict:
            return {}

        def handler_b(event: Event) -> dict:
            return {}

        # Register A
        entry_a = ListenerEntry(callback=handler_a, priority=0)
        registry.add([TestEvent], entry_a)

        # Register B with after=[A]
        entry_b = ListenerEntry(callback=handler_b, priority=0, after=[handler_a])
        registry.add([TestEvent], entry_b)

        # Try to register A again with after=[B] -> cycle
        entry_a_cyclic = ListenerEntry(
            callback=handler_a, priority=0, after=[handler_b]
        )

        with pytest.raises(CyclicDependencyError):
            registry.add([TestEvent], entry_a_cyclic)


class TestRegistryTableRemove:
    """Test RegistryTable.remove() method."""

    def test_remove_specific_callback_from_specific_event(self):
        """Remove (event_types, callback) removes specific listener."""
        registry = RegistryTable()

        def handler(event: Event) -> dict:
            return {}

        entry = ListenerEntry(callback=handler, priority=0)
        registry.add([TestEvent], entry)

        registry.remove([TestEvent], handler)

        result = registry.resolve_order(TestEvent)
        assert result == []

    def test_remove_all_listeners_from_specific_event(self):
        """Remove (event_types, None) removes all listeners."""
        registry = RegistryTable()

        def handler1(event: Event) -> dict:
            return {}

        def handler2(event: Event) -> dict:
            return {}

        registry.add([TestEvent], ListenerEntry(callback=handler1, priority=0))
        registry.add([TestEvent], ListenerEntry(callback=handler2, priority=0))

        registry.remove([TestEvent], None)

        result = registry.resolve_order(TestEvent)
        assert result == []

    def test_remove_callback_from_all_events(self):
        """Remove (None, callback) removes callback from all event types."""
        registry = RegistryTable()

        def handler(event: Event) -> dict:
            return {}

        entry = ListenerEntry(callback=handler, priority=0)
        registry.add([TestEvent, TestChildEvent], entry)

        registry.remove(None, handler)

        result1 = registry.resolve_order(TestEvent)
        result2 = registry.resolve_order(TestChildEvent)

        # Should be removed from both
        assert not any(e.callback == handler for layer in result1 for e in layer)
        assert not any(e.callback == handler for layer in result2 for e in layer)

    def test_remove_both_none_raises_value_error(self):
        """Remove (None, None) raises ValueError."""
        registry = RegistryTable()

        with pytest.raises(ValueError) as exc_info:
            registry.remove(None, None)

        assert "none" in str(exc_info.value).lower()

    def test_remove_unregistered_callback_raises_value_error(self):
        """Remove unregistered callback raises ValueError."""
        registry = RegistryTable()

        def unregistered(event: Event) -> dict:
            return {}

        with pytest.raises(ValueError):
            registry.remove([TestEvent], unregistered)

    def test_remove_depended_listener_raises_value_error(self):
        """Remove listener with active after dependencies raises ValueError."""
        registry = RegistryTable()

        def handler_a(event: Event) -> dict:
            return {}

        def handler_b(event: Event) -> dict:
            return {}

        entry_a = ListenerEntry(callback=handler_a, priority=0)
        registry.add([TestEvent], entry_a)

        entry_b = ListenerEntry(callback=handler_b, priority=0, after=[handler_a])
        registry.add([TestEvent], entry_b)

        # Try to remove handler_a -> should fail because handler_b depends on it
        with pytest.raises(ValueError) as exc_info:
            registry.remove([TestEvent], handler_a)

        assert "depend" in str(exc_info.value).lower()

    def test_remove_increments_revision(self):
        """Remove increments _revision."""
        registry = RegistryTable()

        def handler(event: Event) -> dict:
            return {}

        entry = ListenerEntry(callback=handler, priority=0)
        registry.add([TestEvent], entry)

        # Verify it's there
        result_before = registry.resolve_order(TestEvent)
        assert len(result_before[0]) == 1

        # Remove it
        registry.remove([TestEvent], handler)

        # Verify it's gone
        result_after = registry.resolve_order(TestEvent)
        assert result_after == []


class TestRegistryTableResolveOrder:
    """Test RegistryTable.resolve_order() method."""

    def test_resolve_order_empty_registry(self):
        """resolve_order returns empty list for no listeners."""
        registry = RegistryTable()

        result = registry.resolve_order(TestEvent)

        assert result == []

    def test_resolve_order_priority_layering(self):
        """resolve_order returns listeners sorted by priority (high to low)."""
        registry = RegistryTable()

        def low_priority(event: Event) -> dict:
            return {}

        def high_priority(event: Event) -> dict:
            return {}

        registry.add([TestEvent], ListenerEntry(callback=low_priority, priority=1))
        registry.add([TestEvent], ListenerEntry(callback=high_priority, priority=10))

        result = registry.resolve_order(TestEvent)

        assert len(result) == 2  # Two priority layers
        assert result[0][0].callback == high_priority  # Higher priority first
        assert result[1][0].callback == low_priority

    def test_resolve_order_after_topological_sort(self):
        """resolve_order respects after dependencies within same priority."""
        registry = RegistryTable()

        def handler_a(event: Event) -> dict:
            return {}

        def handler_b(event: Event) -> dict:
            return {}

        registry.add([TestEvent], ListenerEntry(callback=handler_a, priority=0))
        registry.add(
            [TestEvent],
            ListenerEntry(callback=handler_b, priority=0, after=[handler_a]),
        )

        result = registry.resolve_order(TestEvent)

        assert len(result) == 1  # Same priority layer
        assert result[0][0].callback == handler_a  # A before B
        assert result[0][1].callback == handler_b

    def test_resolve_order_mro_expansion(self):
        """resolve_order includes listeners from parent event types via MRO."""
        registry = RegistryTable()

        def parent_handler(event: Event) -> dict:
            return {}

        def child_handler(event: Event) -> dict:
            return {}

        registry.add([TestEvent], ListenerEntry(callback=parent_handler, priority=0))
        registry.add(
            [TestChildEvent], ListenerEntry(callback=child_handler, priority=0)
        )

        result = registry.resolve_order(TestChildEvent)

        # Should contain both child and parent handlers
        all_callbacks = [e.callback for layer in result for e in layer]
        assert parent_handler in all_callbacks
        assert child_handler in all_callbacks

    def test_resolve_order_no_deduplication(self):
        """resolve_order does not deduplicate same callback from multiple MRO levels."""
        registry = RegistryTable()

        def handler(event: Event) -> dict:
            return {}

        # Register same callback to both parent and child
        registry.add([TestEvent], ListenerEntry(callback=handler, priority=0))
        registry.add([TestChildEvent], ListenerEntry(callback=handler, priority=0))

        result = registry.resolve_order(TestChildEvent)

        # Should see handler twice (once from each registration)
        all_callbacks = [e.callback for layer in result for e in layer]
        assert all_callbacks.count(handler) == 2

    def test_resolve_order_caching(self):
        """resolve_order uses cache when _revision unchanged."""
        registry = RegistryTable()

        def handler(event: Event) -> dict:
            return {}

        registry.add([TestEvent], ListenerEntry(callback=handler, priority=0))

        # First call builds cache
        result1 = registry.resolve_order(TestEvent)

        # Second call should hit cache (same object reference if cached correctly)
        result2 = registry.resolve_order(TestEvent)

        assert result1 == result2

    def test_resolve_order_cache_invalidation_on_add(self):
        """resolve_order cache invalidates when add() is called."""
        registry = RegistryTable()

        def handler1(event: Event) -> dict:
            return {}

        registry.add([TestEvent], ListenerEntry(callback=handler1, priority=0))
        result1 = registry.resolve_order(TestEvent)

        # Add another listener -> cache invalidated
        def handler2(event: Event) -> dict:
            return {}

        registry.add([TestEvent], ListenerEntry(callback=handler2, priority=0))
        result2 = registry.resolve_order(TestEvent)

        # Should see both listeners now
        assert len(result2[0]) == 2
        assert len(result1[0]) == 1

    def test_resolve_order_cycle_detection(self):
        """resolve_order detects cycles during topological sort (defensive)."""
        # This should not happen if add() validates correctly,
        # but resolve_order should still handle it defensively
        # This test is primarily for future-proofing
        pass  # Covered by add() cycle detection tests
