"""Shared type definitions for affairon.

This module contains type aliases used across multiple components.
Centralizing these definitions ensures consistency and makes future
type changes easier to manage.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from affairon.affairs import MutableAffair

StandardResultT = dict[str, Any] | None
CallbackT = Callable[[MutableAffair], StandardResultT]
AsyncCallbackT = Callable[[MutableAffair], Coroutine[Any, Any, StandardResultT]]
