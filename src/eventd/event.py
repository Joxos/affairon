"""Event model for eventd.

This module provides the Event base class and MetaEvent framework for
event-driven architecture.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from eventd.exceptions import EventValidationError


class Event(BaseModel):
    """Base class for all events.

    Users should inherit from this class to define custom events with
    additional fields. Instances are immutable (frozen).

    Example:
        >>> class UserEvent(Event):
        ...     user_id: int
        ...     action: str
        >>> event = UserEvent(user_id=123, action="login")

    Raises:
        EventValidationError: If fields fail pydantic validation.
    """

    model_config = ConfigDict(frozen=True)

    def __init__(self, **data: Any) -> None:
        """Wrap pydantic ValidationError into EventValidationError."""
        try:
            super().__init__(**data)
        except ValidationError as exc:
            raise EventValidationError(str(exc)) from exc


class MetaEvent(Event):
    """Base class for framework meta-events.

    MetaEvent describes framework internal behaviors (errors, dead letters, etc.).
    Users can register listeners on MetaEvent subclasses to observe and extend
    framework behavior.

    Note:
        MVP stage only defines MetaEvent types without auto-emission.
        Future versions will emit MetaEvents for error handling and observability.
    """


class CallbackErrorEvent(MetaEvent):
    """Meta-event emitted when a listener raises an exception.

    Attributes:
        listener_name: Name of the failed listener.
        original_event_type: Type name of the event being processed.
        error_message: Exception message.
        error_type: Exception type name.
    """

    listener_name: str
    original_event_type: str
    error_message: str
    error_type: str


class EventDeadLetteredEvent(MetaEvent):
    """Meta-event emitted when an event enters the dead letter queue.

    Attributes:
        listener_name: Name of the listener that failed processing.
        original_event_type: Type name of the dead-lettered event.
        error_message: Reason for entering dead letter queue.
        retry_count: Number of retry attempts before dead-lettering.
    """

    listener_name: str
    original_event_type: str
    error_message: str
    retry_count: int
