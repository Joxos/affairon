"""Affair model for affairon.

This module provides the Affair base class and MetaAffair framework for
affair-driven architecture.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from affairon.exceptions import AffairValidationError


class MutableAffair(BaseModel):
    """Mutable version of Affair. Also serves as base class for Affair to wrap pydantic validation."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid", strict=True)

    def __init__(self, **data: Any) -> None:
        """Wrap pydantic ValidationError into AffairValidationError."""
        try:
            super().__init__(**data)
        except ValidationError as exc:
            raise AffairValidationError(str(exc)) from exc


class Affair(MutableAffair):
    """Base class for all affairs.

    Users should inherit from this class to define custom affairs with
    additional fields. Instances are immutable (frozen).

    Example:
        >>> class UserAffair(Affair):
        ...     user_id: int
        ...     action: str
        >>> affair = UserAffair(user_id=123, action="login")

    Raises:
        AffairValidationError: If fields fail pydantic validation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class MetaAffair(Affair):
    """Base class for framework meta-affairs.

    MetaAffair describes framework-level lifecycle and observability affairs.
    Users can register listeners on MetaAffair subclasses to hook into
    framework behavior (e.g. application start via ``AffairMain``, error
    handling via ``CallbackErrorAffair``).
    """


class CallbackErrorAffair(MetaAffair):
    """Meta-affair emitted when a listener raises an exception.

    Attributes:
        listener_name: Name of the failed listener.
        original_affair_type: Type name of the affair being processed.
        error_message: Exception message.
        error_type: Exception type name.
    """

    listener_name: str
    original_affair_type: str
    error_message: str
    error_type: str


class AffairDeadLetteredAffair(MetaAffair):
    """Meta-affair emitted when an affair enters the dead letter queue.

    Attributes:
        listener_name: Name of the listener that failed processing.
        original_affair_type: Type name of the dead-lettered affair.
        error_message: Reason for entering dead letter queue.
        retry_count: Number of retry attempts before dead-lettering.
    """

    listener_name: str
    original_affair_type: str
    error_message: str
    retry_count: int


class AffairMain(MetaAffair):
    """Meta-affair emitted by fairun to start the application.

    The CLI runner ``fairun`` reads ``pyproject.toml``, composes plugins,
    then emits this affair on the default dispatcher.  User applications
    register a callback on ``AffairMain`` to define their entry point.

    Attributes:
        project_path: Resolved path to the project directory.
    """

    project_path: Path = Path(".").resolve()


class AffairAwareMeta(type):
    """Metaclass that registers ``@dispatcher.on_method()`` callbacks.

    Overrides ``__call__`` so that ``_bind_affair_methods()`` runs
    *after* ``__init__`` returns, regardless of whether the subclass
    calls ``super().__init__()``.
    """

    def __call__(cls, *args: Any, **kwargs: Any) -> Any:
        instance = super().__call__(*args, **kwargs)
        instance._bind_affair_methods()
        return instance


class AffairAware(metaclass=AffairAwareMeta):
    """Mixin that auto-registers ``@dispatcher.on_method()`` decorated methods.

    Methods decorated with ``@dispatcher.on_method()`` inside an
    ``AffairAware`` subclass are not registered at class definition time.
    Instead, the decorator stamps metadata on the unbound function, and
    the ``AffairAwareMeta`` metaclass registers the *bound* methods
    automatically after ``__init__`` completes.

    Use ``on_method()`` (not ``on()``) for class methods.
    No ``super().__init__()`` call is required.

    ``@staticmethod`` and ``@classmethod`` are supported — place them
    **outside** ``@on_method()``:

    Example::

        class Kitchen(AffairAware):
            @dispatcher.on_method(AddIngredients)
            def cook(self, affair: AddIngredients) -> dict[str, list[str]]:
                return {"dish": ["eggs"]}

            @staticmethod
            @dispatcher.on_method(AddIngredients)
            def garnish(affair: AddIngredients) -> dict[str, str]:
                return {"garnish": "parsley"}

        k = Kitchen()  # cook() and garnish() are now registered
    """

    def _bind_affair_methods(self) -> None:
        """Scan for marked methods and register them as bound callbacks."""
        # Collect marked methods across MRO, build unbound → bound mapping
        unbound_to_bound: dict[Any, Any] = {}
        marked: list[Any] = []

        seen: set[str] = set()
        for klass in type(self).__mro__:
            for name, attr in vars(klass).items():
                if name in seen:
                    continue
                # Unwrap staticmethod/classmethod to access inner function
                inner = attr
                if isinstance(attr, (staticmethod, classmethod)):
                    inner = attr.__func__
                if callable(inner) and hasattr(inner, "_affair_types"):
                    unbound_to_bound[inner] = getattr(self, name)
                    marked.append(inner)
                    seen.add(name)

        # Register each bound method, resolving after references
        for func in marked:
            bound = unbound_to_bound[func]
            after = func._affair_after
            if after:
                after = [unbound_to_bound.get(cb, cb) for cb in after]
            func._affair_dispatcher.register(func._affair_types, bound, after=after)
