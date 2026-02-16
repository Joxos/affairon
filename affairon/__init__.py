"""affairon - A flexible affair-driven framework for Python.

This package provides affair-driven architecture support with both synchronous
and asynchronous dispatch modes.
"""

__version__ = "0.1.0"

from affairon.async_dispatcher import AsyncDispatcher
from affairon.dispatcher import Dispatcher
from affairon.affairs import CallbackErrorAffair, Affair, AffairDeadLetteredAffair, MetaAffair, MutableAffair
from affairon.exceptions import (
    CyclicDependencyError,
    AffairdError,
    AffairValidationError,
    KeyConflictError,
)

# Module-level default dispatcher instance
default_dispatcher = Dispatcher()

__all__ = [
    # Version
    "__version__",
    # Affair classes
    "Affair",
    "MetaAffair",
    "CallbackErrorAffair",
    "AffairDeadLetteredAffair",
    "MutableAffair",
    # Dispatcher classes
    "Dispatcher",
    "AsyncDispatcher",
    "default_dispatcher",
    # Exception classes
    "AffairdError",
    "AffairValidationError",
    "CyclicDependencyError",
    "KeyConflictError",
]
