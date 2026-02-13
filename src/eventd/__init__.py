"""eventd - A flexible event-driven framework for Python.

This package provides event-driven architecture support with both synchronous
and asynchronous dispatch modes.
"""

__version__ = "0.1.0"

from eventd.dispatcher import AsyncDispatcher, Dispatcher
from eventd.event import CallbackErrorEvent, Event, EventDeadLetteredEvent, MetaEvent
from eventd.exceptions import (
    CyclicDependencyError,
    EventdError,
    EventValidationError,
    KeyConflictError,
)

# Module-level default dispatcher instance
default_dispatcher = Dispatcher()

__all__ = [
    # Version
    "__version__",
    # Event classes
    "Event",
    "MetaEvent",
    "CallbackErrorEvent",
    "EventDeadLetteredEvent",
    # Dispatcher classes
    "Dispatcher",
    "AsyncDispatcher",
    "default_dispatcher",
    # Exception classes
    "EventdError",
    "EventValidationError",
    "CyclicDependencyError",
    "KeyConflictError",
]
