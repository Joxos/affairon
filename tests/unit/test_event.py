"""Tests for Event and MetaEvent classes.

Tests verify:
- Event inherits from pydantic BaseModel with frozen=True
- event_id and timestamp are framework reserved fields
- Reserved fields cannot be provided by users
- User-defined fields pass through pydantic validation
- EventValidationError wraps pydantic ValidationError
- MetaEvent and its subclasses are properly defined
"""

import pytest
from pydantic import ValidationError as PydanticValidationError

from eventd.event import Event, EventDeadLetteredEvent, ListenerErrorEvent, MetaEvent
from eventd.exceptions import EventValidationError


class TestEventBasics:
    """Test Event base class basic properties."""

    def test_event_inherits_from_base_model(self):
        """Event inherits from pydantic BaseModel."""
        from pydantic import BaseModel

        assert issubclass(Event, BaseModel)

    def test_event_is_frozen(self):
        """Event instances are frozen (immutable after creation)."""

        class TestEvent(Event):
            data: str

        event = TestEvent(data="test")
        with pytest.raises((AttributeError, PydanticValidationError)):
            event.data = "modified"

    def test_event_id_defaults_to_none(self):
        """event_id defaults to None before injection."""

        class TestEvent(Event):
            data: str

        event = TestEvent(data="test")
        assert event.event_id is None

    def test_timestamp_defaults_to_none(self):
        """timestamp defaults to None before injection."""

        class TestEvent(Event):
            data: str

        event = TestEvent(data="test")
        assert event.timestamp is None


class TestReservedFields:
    """Test reserved field protection."""

    def test_reject_event_id_in_constructor(self):
        """Providing event_id in constructor raises EventValidationError."""

        class TestEvent(Event):
            data: str

        with pytest.raises(EventValidationError) as exc_info:
            TestEvent(data="test", event_id=123)

        assert "event_id" in str(exc_info.value).lower()

    def test_reject_timestamp_in_constructor(self):
        """Providing timestamp in constructor raises EventValidationError."""

        class TestEvent(Event):
            data: str

        with pytest.raises(EventValidationError) as exc_info:
            TestEvent(data="test", timestamp=1234567890.0)

        assert "timestamp" in str(exc_info.value).lower()

    def test_reject_both_reserved_fields(self):
        """Providing both reserved fields raises EventValidationError."""

        class TestEvent(Event):
            data: str

        with pytest.raises(EventValidationError):
            TestEvent(data="test", event_id=123, timestamp=1234567890.0)


class TestUserDefinedFields:
    """Test user-defined field validation."""

    def test_create_event_with_valid_fields(self):
        """Event with valid user fields is created successfully."""

        class UserEvent(Event):
            user_id: int
            action: str

        event = UserEvent(user_id=123, action="login")
        assert event.user_id == 123
        assert event.action == "login"

    def test_pydantic_validation_wrapped_in_eventd_error(self):
        """Pydantic validation errors are wrapped in EventValidationError."""

        class UserEvent(Event):
            user_id: int
            action: str

        with pytest.raises(EventValidationError):
            UserEvent(user_id="not_an_int", action="login")

    def test_missing_required_field_raises_eventd_error(self):
        """Missing required fields raise EventValidationError."""

        class UserEvent(Event):
            user_id: int
            action: str

        with pytest.raises(EventValidationError):
            UserEvent(user_id=123)


class TestEventInheritance:
    """Test event inheritance works correctly."""

    def test_create_derived_event(self):
        """Can create events derived from Event."""

        class BaseUserEvent(Event):
            user_id: int

        class LoginEvent(BaseUserEvent):
            ip_address: str

        event = LoginEvent(user_id=123, ip_address="127.0.0.1")
        assert event.user_id == 123
        assert event.ip_address == "127.0.0.1"
        assert event.event_id is None
        assert event.timestamp is None


class TestMetaEvent:
    """Test MetaEvent base class."""

    def test_meta_event_inherits_from_event(self):
        """MetaEvent inherits from Event."""
        assert issubclass(MetaEvent, Event)

    def test_meta_event_has_reserved_fields(self):
        """MetaEvent instances have event_id and timestamp fields."""
        meta = MetaEvent()
        assert meta.event_id is None
        assert meta.timestamp is None


class TestListenerErrorEvent:
    """Test ListenerErrorEvent meta-event."""

    def test_listener_error_event_inherits_from_meta_event(self):
        """ListenerErrorEvent inherits from MetaEvent."""
        assert issubclass(ListenerErrorEvent, MetaEvent)

    def test_listener_error_event_has_required_fields(self):
        """ListenerErrorEvent has all required fields."""
        event = ListenerErrorEvent(
            listener_name="test_listener",
            original_event_type="UserEvent",
            error_message="Division by zero",
            error_type="ZeroDivisionError",
        )
        assert event.listener_name == "test_listener"
        assert event.original_event_type == "UserEvent"
        assert event.error_message == "Division by zero"
        assert event.error_type == "ZeroDivisionError"

    def test_listener_error_event_rejects_reserved_fields(self):
        """ListenerErrorEvent rejects reserved fields in constructor."""
        with pytest.raises(EventValidationError):
            ListenerErrorEvent(
                listener_name="test",
                original_event_type="UserEvent",
                error_message="error",
                error_type="Error",
                event_id=123,
            )


class TestEventDeadLetteredEvent:
    """Test EventDeadLetteredEvent meta-event."""

    def test_event_dead_lettered_event_inherits_from_meta_event(self):
        """EventDeadLetteredEvent inherits from MetaEvent."""
        assert issubclass(EventDeadLetteredEvent, MetaEvent)

    def test_event_dead_lettered_event_has_required_fields(self):
        """EventDeadLetteredEvent has all required fields."""
        event = EventDeadLetteredEvent(
            listener_name="test_listener",
            original_event_type="UserEvent",
            error_message="Max retries exceeded",
            retry_count=3,
        )
        assert event.listener_name == "test_listener"
        assert event.original_event_type == "UserEvent"
        assert event.error_message == "Max retries exceeded"
        assert event.retry_count == 3

    def test_event_dead_lettered_event_rejects_reserved_fields(self):
        """EventDeadLetteredEvent rejects reserved fields in constructor."""
        with pytest.raises(EventValidationError):
            EventDeadLetteredEvent(
                listener_name="test",
                original_event_type="UserEvent",
                error_message="error",
                retry_count=3,
                timestamp=1234567890.0,
            )
