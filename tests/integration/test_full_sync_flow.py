"""Integration tests for synchronous event flow."""

import pytest

from eventd import (
    AsyncDispatcher,
    CyclicDependencyError,
    Dispatcher,
    Event,
    EventdError,
    default_dispatcher,
)


class UserRegisteredEvent(Event):
    """User registration event."""

    username: str
    email: str


class EmailEvent(Event):
    """Email notification event."""

    recipient: str
    subject: str


class ParentEvent(Event):
    """Parent event for MRO testing."""

    data: str


class ChildEvent(ParentEvent):
    """Child event for MRO testing."""

    extra: str = "default"


class TestSyncIntegration:
    """Integration tests for sync dispatcher."""

    def test_complete_sync_flow(self):
        """Complete sync flow: define event -> register listeners -> emit."""
        dispatcher = Dispatcher()
        execution_order = []

        @dispatcher.on(UserRegisteredEvent)
        def send_welcome_email(event: UserRegisteredEvent) -> dict:
            execution_order.append("send_welcome_email")
            return {"email_sent": True}

        @dispatcher.on(UserRegisteredEvent)
        def log_registration(event: UserRegisteredEvent) -> dict:
            execution_order.append("log_registration")
            return {"logged": True}

        event = UserRegisteredEvent(username="alice", email="alice@example.com")
        result = dispatcher.emit(event)

        assert event.event_id == 0
        assert event.timestamp is not None
        assert result == {"email_sent": True, "logged": True}
        assert len(execution_order) == 2

    def test_mro_priority_after_combination(self):
        """MRO + priority + after combination."""
        dispatcher = Dispatcher()
        execution_order = []

        @dispatcher.on(ParentEvent, priority=10)
        def handler_high_priority(event: ParentEvent) -> None:
            execution_order.append("high_priority")

        @dispatcher.on(ParentEvent, priority=0)
        def handler_low_priority(event: ParentEvent) -> None:
            execution_order.append("low_priority")

        @dispatcher.on(ChildEvent, after=[handler_low_priority])
        def handler_after_low(event: ChildEvent) -> None:
            execution_order.append("after_low")

        event = ChildEvent(data="test", extra="child")
        dispatcher.emit(event)

        # Expected order:
        # 1. high_priority (priority 10)
        # 2. low_priority (priority 0)
        # 3. after_low (depends on low_priority)
        assert execution_order == ["high_priority", "low_priority", "after_low"]

    def test_recursive_emit(self):
        """Recursive emit within listener."""
        dispatcher = Dispatcher()
        execution_order = []

        @dispatcher.on(UserRegisteredEvent)
        def trigger_email_event(event: UserRegisteredEvent) -> None:
            execution_order.append("user_registered")
            # Recursively emit email event
            email_event = EmailEvent(
                recipient=event.email, subject="Welcome to our platform"
            )
            dispatcher.emit(email_event)

        @dispatcher.on(EmailEvent)
        def send_email(event: EmailEvent) -> None:
            execution_order.append("email_sent")

        event = UserRegisteredEvent(username="bob", email="bob@example.com")
        dispatcher.emit(event)

        assert execution_order == ["user_registered", "email_sent"]

    def test_shutdown_prevents_emit(self):
        """shutdown() prevents subsequent emit()."""
        dispatcher = Dispatcher()

        @dispatcher.on(UserRegisteredEvent)
        def handler(event: UserRegisteredEvent) -> None:
            pass

        dispatcher.shutdown()

        with pytest.raises(RuntimeError, match="shut down"):
            dispatcher.emit(UserRegisteredEvent(username="test", email="test@test.com"))

    def test_default_dispatcher_available(self):
        """Module-level default_dispatcher is available and functional."""
        execution_count = []

        @default_dispatcher.on(UserRegisteredEvent)
        def handler(event: UserRegisteredEvent) -> dict:
            execution_count.append(1)
            return {"handled": True}

        event = UserRegisteredEvent(username="default_test", email="test@test.com")
        result = default_dispatcher.emit(event)

        assert result == {"handled": True}
        assert len(execution_count) == 1

        # Clean up
        default_dispatcher.unregister(callback=handler)


class TestAsyncIntegration:
    """Integration tests for async dispatcher."""

    @pytest.mark.asyncio
    async def test_complete_async_flow(self):
        """Complete async flow: define event -> register listeners -> emit."""
        dispatcher = AsyncDispatcher()
        execution_order = []

        @dispatcher.on(UserRegisteredEvent)
        async def send_welcome_email(event: UserRegisteredEvent) -> dict:
            execution_order.append("send_welcome_email")
            return {"email_sent": True}

        @dispatcher.on(UserRegisteredEvent)
        async def log_registration(event: UserRegisteredEvent) -> dict:
            execution_order.append("log_registration")
            return {"logged": True}

        event = UserRegisteredEvent(username="alice", email="alice@example.com")
        result = await dispatcher.emit(event)

        assert event.event_id == 0
        assert event.timestamp is not None
        assert result == {"email_sent": True, "logged": True}
        assert len(execution_order) == 2

    @pytest.mark.asyncio
    async def test_async_recursive_emit(self):
        """Async recursive emit within listener."""
        dispatcher = AsyncDispatcher()
        execution_order = []

        @dispatcher.on(UserRegisteredEvent)
        async def trigger_email_event(event: UserRegisteredEvent) -> None:
            execution_order.append("user_registered")
            email_event = EmailEvent(
                recipient=event.email, subject="Welcome to our platform"
            )
            await dispatcher.emit(email_event)

        @dispatcher.on(EmailEvent)
        async def send_email(event: EmailEvent) -> None:
            execution_order.append("email_sent")

        event = UserRegisteredEvent(username="bob", email="bob@example.com")
        await dispatcher.emit(event)

        assert execution_order == ["user_registered", "email_sent"]

    @pytest.mark.asyncio
    async def test_async_shutdown_prevents_emit(self):
        """shutdown() prevents subsequent emit()."""
        dispatcher = AsyncDispatcher()

        @dispatcher.on(UserRegisteredEvent)
        async def handler(event: UserRegisteredEvent) -> None:
            pass

        await dispatcher.shutdown()

        with pytest.raises(RuntimeError, match="shut down"):
            await dispatcher.emit(
                UserRegisteredEvent(username="test", email="test@test.com")
            )


class TestErrorHandling:
    """Integration tests for error handling."""

    def test_import_all_exceptions(self):
        """All exception classes are importable from main package."""
        from eventd import (
            CyclicDependencyError,
            EventValidationError,
            KeyConflictError,
        )

        # Verify inheritance
        assert issubclass(EventValidationError, EventdError)
        assert issubclass(CyclicDependencyError, EventdError)
        assert issubclass(KeyConflictError, EventdError)

    def test_cyclic_dependency_detection(self):
        """Cyclic dependency is properly detected and raises error."""
        dispatcher = Dispatcher()

        @dispatcher.on(UserRegisteredEvent)
        def handler_a(event: UserRegisteredEvent) -> None:
            pass

        @dispatcher.on(UserRegisteredEvent, after=[handler_a])
        def handler_b(event: UserRegisteredEvent) -> None:
            pass

        # This WOULD create a cycle if we could re-register handler_a
        # Since Python doesn't allow decorator re-registration easily,
        # we test via register() method
        with pytest.raises(CyclicDependencyError):
            dispatcher.register(
                UserRegisteredEvent,
                handler_a,
                after=[handler_b],  # Creates A→B→A cycle
            )

    def test_key_conflict_error(self):
        """KeyConflictError is raised on duplicate result keys."""
        dispatcher = Dispatcher()

        @dispatcher.on(UserRegisteredEvent)
        def handler1(event: UserRegisteredEvent) -> dict:
            return {"status": "ok"}

        @dispatcher.on(UserRegisteredEvent)
        def handler2(event: UserRegisteredEvent) -> dict:
            return {"status": "error"}  # Conflict!

        from eventd import KeyConflictError

        with pytest.raises(KeyConflictError):
            dispatcher.emit(UserRegisteredEvent(username="test", email="test@test.com"))


class TestMetaEvents:
    """Integration tests for meta-events."""

    def test_meta_event_classes_importable(self):
        """MetaEvent classes are importable from main package."""
        from eventd import EventDeadLetteredEvent, ListenerErrorEvent, MetaEvent

        assert issubclass(ListenerErrorEvent, MetaEvent)
        assert issubclass(EventDeadLetteredEvent, MetaEvent)

    def test_create_meta_events(self):
        """Meta-events can be instantiated."""
        from eventd import EventDeadLetteredEvent, ListenerErrorEvent

        error_event = ListenerErrorEvent(
            listener_name="test_handler",
            original_event_type="UserRegisteredEvent",
            error_message="Test error",
            error_type="RuntimeError",
        )
        assert error_event.listener_name == "test_handler"

        dead_letter_event = EventDeadLetteredEvent(
            listener_name="test_handler",
            original_event_type="UserRegisteredEvent",
            error_message="Max retries exceeded",
            retry_count=3,
        )
        assert dead_letter_event.retry_count == 3
