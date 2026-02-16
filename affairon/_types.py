"""Shared type definitions for affairon.

This module contains type aliases used across multiple components.
Centralizing these definitions ensures consistency and makes future
type changes easier to manage.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from affairon.affair import Affair

StandardResultT = dict[str, Any] | None
CallbackT = Callable[[Affair], StandardResultT]
AsyncCallbackT = Callable[[Affair], Coroutine[Any, Any, StandardResultT]]
