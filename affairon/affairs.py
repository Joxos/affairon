"""Affair models for affairon.

Defines the affair type hierarchy: MutableAffair, Affair, MetaAffair,
and framework meta-affairs (AffairMain, CallbackErrorAffair, etc.).
"""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from affairon.exceptions import AffairValidationError

type MergeStrategy = Literal["raise", "keep", "override", "list_merge", "dict_merge"]
"""Strategy for resolving key conflicts when merging callback results.

- ``raise``: Raise :class:`KeyConflictError` on duplicate keys (default).
- ``keep``: Keep the first value, discard later duplicates.
- ``override``: Last value wins, silently replaces earlier ones.
- ``list_merge``: Collect all values into a list per key.
- ``dict_merge``: Collect all values into a dict keyed by callback name.
"""


class MutableAffair(BaseModel):
    """Mutable version of Affair.

    Also serves as base class for Affair to wrap pydantic validation.

    Attributes:
        emit_up: When True, emitting this affair also triggers callbacks
            registered on parent affair types, walking the MRO from child
            to parent.  Defaults to False (only the concrete type fires).
        merge_strategy: Strategy for resolving key conflicts when merging
            callback results.  Defaults to ``"raise"``.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid", strict=True)

    emit_up: bool = False
    merge_strategy: MergeStrategy = "raise"

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
