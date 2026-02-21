"""affairon - A flexible affair-driven framework for Python.

This package provides affair-driven architecture support with both synchronous
and asynchronous dispatch modes.
"""

__version__ = "0.1.0"

from loguru import logger

# Disable all affairon logging by default.  Users opt in with:
#     from loguru import logger
#     logger.enable("affairon")
logger.disable("affairon")

from affairon.affairs import (
    Affair,
    AffairDeadLetteredAffair,
    AffairMain,
    CallbackErrorAffair,
    MetaAffair,
    MutableAffair,
)
from affairon.async_dispatcher import AsyncDispatcher
from affairon.aware import AffairAware
from affairon.dispatcher import Dispatcher
from affairon.exceptions import (
    AffairError,
    AffairValidationError,
    CyclicDependencyError,
    KeyConflictError,
    PluginEntryPointError,
    PluginError,
    PluginImportError,
    PluginNotFoundError,
    PluginVersionError,
)

# Module-level default dispatcher instance
default_dispatcher = Dispatcher()

__all__ = [
    # Version
    "__version__",
    # Affair classes
    "Affair",
    "MetaAffair",
    "AffairMain",
    "AffairAware",
    "CallbackErrorAffair",
    "AffairDeadLetteredAffair",
    "MutableAffair",
    # Dispatcher classes
    "Dispatcher",
    "AsyncDispatcher",
    "default_dispatcher",
    # Exception classes
    "AffairError",
    "AffairValidationError",
    "CyclicDependencyError",
    "KeyConflictError",
    "PluginError",
    "PluginNotFoundError",
    "PluginVersionError",
    "PluginEntryPointError",
    "PluginImportError",
]
