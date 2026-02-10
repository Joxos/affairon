"""Shared type definitions for eventd.

This module contains type aliases used across multiple components.
Centralizing these definitions ensures consistency and makes future
type changes easier to manage.
"""

from collections.abc import Awaitable, Callable
from typing import Any

# Forward reference to Event class (defined in event.py)
# Using string literal to avoid circular import
Event = Any  # Will be properly typed as eventd.Event at runtime

# Synchronous listener callback signature
# Takes an Event, returns a dict or None
ListenerCallback = Callable[[Event], dict[str, Any] | None]

# Asynchronous listener callback signature
# Takes an Event, returns an awaitable that resolves to dict or None
AsyncListenerCallback = Callable[[Event], Awaitable[dict[str, Any] | None]]

# Event ID generator function signature
# Returns a unique integer for each event
EventIdGenerator = Callable[[], int]

# Timestamp generator function signature
# Returns a float timestamp (typically from time.time())
TimestampGenerator = Callable[[], float]
