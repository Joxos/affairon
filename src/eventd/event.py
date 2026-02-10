"""Event model for eventd.

This module provides the Event base class and MetaEvent framework for
event-driven architecture.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from eventd.exceptions import EventValidationError


class Event(BaseModel):
    """Base class for all events.

    Users should inherit from this class to define custom events with
    additional fields. The event_id and timestamp fields are reserved
    and will be injected by the Dispatcher during emit().

    Example:
        >>> class UserEvent(Event):
        ...     user_id: int
        ...     action: str
        >>> event = UserEvent(user_id=123, action="login")
        >>> # event_id and timestamp are None until emit()

    Attributes:
        event_id: Unique integer identifier (injected by Dispatcher).
        timestamp: Float timestamp in seconds (injected by Dispatcher).
    """

    model_config = ConfigDict(frozen=True)

    event_id: int | None = Field(default=None, init=False)
    timestamp: float | None = Field(default=None, init=False)

    @model_validator(mode="before")
    @classmethod
    def _reject_reserved_fields(cls, data: Any) -> Any:
        """Reject user-provided reserved fields.

        Args:
            data: User-provided data.

        Returns:
            Validated data.

        Raises:
            EventValidationError: If reserved fields are provided.
        """
        if isinstance(data, dict):
            reserved = {"event_id", "timestamp"}
            provided = reserved & set(data.keys())
            if provided:
                raise EventValidationError(
                    f"Reserved fields cannot be provided by user: {provided}"
                )
        return data

    def __init__(self, **data: Any) -> None:
        """Initialize event with validation.

        Args:
            **data: Event field values.

        Raises:
            EventValidationError: If validation fails.
        """
        try:
            super().__init__(**data)
        except PydanticValidationError as e:
            raise EventValidationError(str(e)) from e


class MetaEvent(Event):
    """Base class for framework meta-events.

    MetaEvent describes framework internal behaviors (errors, dead letters, etc.).
    Users can register listeners on MetaEvent subclasses to observe and extend
    framework behavior.

    Note:
        MVP stage only defines MetaEvent types without auto-emission.
        Future versions will emit MetaEvents for error handling and observability.
    """


class ListenerErrorEvent(MetaEvent):
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
