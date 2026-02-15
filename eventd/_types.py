"""Shared type definitions for eventd.

This module contains type aliases used across multiple components.
Centralizing these definitions ensures consistency and makes future
type changes easier to manage.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from .event import Event  # Importing Event for type annotations

StandardResultT = dict[str, Any] | None
CallbackT = Callable[[Event], StandardResultT]
AsyncCallbackT = Callable[[Event], Coroutine[Any, Any, StandardResultT]]
