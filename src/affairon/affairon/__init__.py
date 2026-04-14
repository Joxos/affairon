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
    AffairMain,
    CallbackErrorAffair,
    MetaAffair,
    MutableAffair,
)
from affairon.associate import affair, associate
from affairon.async_dispatcher import AsyncDispatcher
from affairon.aware import AffairAware
from affairon.dispatcher import Dispatcher
from affairon.exceptions import (
    AffairError,
    AffairValidationError,
    CyclicDependencyError,
    KeyConflictError,
    PluginConfigError,
    PluginEntryPointError,
    PluginError,
    PluginImportError,
    PluginNotFoundError,
    PluginTargetError,
    PluginVersionError,
)
from affairon.listen import listen
from affairon.locator import Parent, Root
from affairon.node import Node, inject_to, root, route
from affairon.runtime import RuntimeRegistry, inject_from

# Module-level default dispatcher singletons
default_dispatcher = Dispatcher()
default_async_dispatcher = AsyncDispatcher()

__all__ = [
    # Version
    "__version__",
    # Affair classes
    "Affair",
    "MetaAffair",
    "AffairMain",
    "AffairAware",
    "CallbackErrorAffair",
    "MutableAffair",
    # Dispatcher classes
    "Dispatcher",
    "AsyncDispatcher",
    "default_dispatcher",
    "default_async_dispatcher",
    "listen",
    "affair",
    "associate",
    "route",
    "root",
    "inject_to",
    "Node",
    "Root",
    "Parent",
    "RuntimeRegistry",
    "inject_from",
    # Exception classes
    "AffairError",
    "AffairValidationError",
    "CyclicDependencyError",
    "KeyConflictError",
    "PluginError",
    "PluginConfigError",
    "PluginNotFoundError",
    "PluginVersionError",
    "PluginEntryPointError",
    "PluginImportError",
    "PluginTargetError",
]
