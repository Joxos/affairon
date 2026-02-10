"""Tests for Dispatcher and AsyncDispatcher shutdown() functionality."""

import pytest

from eventd.dispatcher import AsyncDispatcher, Dispatcher
from eventd.event import Event


class TestEvent(Event):
    """Test event."""

    data: str


class TestSyncShutdown:
    """Test synchronous Dispatcher.shutdown()."""

    def test_shutdown_sets_shutting_down_flag(self):
        """shutdown() sets internal _is_shutting_down flag."""
        dispatcher = Dispatcher()
        assert dispatcher._is_shutting_down is False

        dispatcher.shutdown()

        assert dispatcher._is_shutting_down is True

    def test_shutdown_prevents_subsequent_emit(self):
        """shutdown() prevents subsequent emit() calls."""
        dispatcher = Dispatcher()
        dispatcher.shutdown()

        with pytest.raises(RuntimeError):
            dispatcher.emit(TestEvent(data="test"))

    def test_shutdown_is_idempotent(self):
        """shutdown() can be called multiple times safely."""
        dispatcher = Dispatcher()

        dispatcher.shutdown()
        dispatcher.shutdown()  # Should not raise

        assert dispatcher._is_shutting_down is True

    def test_shutdown_does_not_affect_registration(self):
        """shutdown() does not prevent listener registration."""
        dispatcher = Dispatcher()
        dispatcher.shutdown()

        # Registration should still work (though emit will fail)
        @dispatcher.on(TestEvent)
        def handler(event: Event) -> dict:
            return {}

        plan = dispatcher._registry.resolve_order(TestEvent)
        assert len(plan) == 1


class TestAsyncShutdown:
    """Test asynchronous AsyncDispatcher.shutdown()."""

    @pytest.mark.asyncio
    async def test_shutdown_sets_shutting_down_flag(self):
        """shutdown() sets internal _is_shutting_down flag."""
        dispatcher = AsyncDispatcher()
        assert dispatcher._is_shutting_down is False

        await dispatcher.shutdown()

        assert dispatcher._is_shutting_down is True

    @pytest.mark.asyncio
    async def test_shutdown_prevents_subsequent_emit(self):
        """shutdown() prevents subsequent emit() calls."""
        dispatcher = AsyncDispatcher()
        await dispatcher.shutdown()

        with pytest.raises(RuntimeError):
            await dispatcher.emit(TestEvent(data="test"))

    @pytest.mark.asyncio
    async def test_shutdown_is_idempotent(self):
        """shutdown() can be called multiple times safely."""
        dispatcher = AsyncDispatcher()

        await dispatcher.shutdown()
        await dispatcher.shutdown()  # Should not raise

        assert dispatcher._is_shutting_down is True

    @pytest.mark.asyncio
    async def test_shutdown_does_not_affect_registration(self):
        """shutdown() does not prevent listener registration."""
        dispatcher = AsyncDispatcher()
        await dispatcher.shutdown()

        # Registration should still work (though emit will fail)
        @dispatcher.on(TestEvent)
        async def handler(event: Event) -> dict:
            return {}

        plan = dispatcher._registry.resolve_order(TestEvent)
        assert len(plan) == 1
