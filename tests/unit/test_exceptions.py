"""Tests for eventd exception hierarchy.

Tests verify:
- Exception inheritance relationships
- Exception can be raised and caught correctly
"""

import pytest

from eventd.exceptions import (
    CyclicDependencyError,
    EventdError,
    EventValidationError,
    KeyConflictError,
)


class TestExceptionHierarchy:
    """Test exception class hierarchy and inheritance."""

    def test_eventd_error_is_base_exception(self):
        """EventdError inherits from Exception."""
        assert issubclass(EventdError, Exception)

    def test_event_validation_error_inheritance(self):
        """EventValidationError inherits from EventdError and ValueError."""
        assert issubclass(EventValidationError, EventdError)
        assert issubclass(EventValidationError, ValueError)

    def test_cyclic_dependency_error_inheritance(self):
        """CyclicDependencyError inherits from EventdError and ValueError."""
        assert issubclass(CyclicDependencyError, EventdError)
        assert issubclass(CyclicDependencyError, ValueError)

    def test_key_conflict_error_inheritance(self):
        """KeyConflictError inherits from EventdError and ValueError."""
        assert issubclass(KeyConflictError, EventdError)
        assert issubclass(KeyConflictError, ValueError)


class TestExceptionRaising:
    """Test exceptions can be raised and caught."""

    def test_raise_eventd_error(self):
        """EventdError can be raised and caught."""
        with pytest.raises(EventdError) as exc_info:
            raise EventdError("test error")
        assert str(exc_info.value) == "test error"

    def test_raise_event_validation_error(self):
        """EventValidationError can be raised and caught."""
        with pytest.raises(EventValidationError) as exc_info:
            raise EventValidationError("validation failed")
        assert str(exc_info.value) == "validation failed"

    def test_raise_cyclic_dependency_error(self):
        """CyclicDependencyError can be raised and caught."""
        with pytest.raises(CyclicDependencyError) as exc_info:
            raise CyclicDependencyError("cycle detected")
        assert str(exc_info.value) == "cycle detected"

    def test_raise_key_conflict_error(self):
        """KeyConflictError can be raised and caught."""
        with pytest.raises(KeyConflictError) as exc_info:
            raise KeyConflictError("key conflict")
        assert str(exc_info.value) == "key conflict"


class TestExceptionCatching:
    """Test exception catching with base class."""

    def test_catch_event_validation_error_as_eventd_error(self):
        """EventValidationError can be caught as EventdError."""
        with pytest.raises(EventdError):
            raise EventValidationError("validation failed")

    def test_catch_cyclic_dependency_error_as_eventd_error(self):
        """CyclicDependencyError can be caught as EventdError."""
        with pytest.raises(EventdError):
            raise CyclicDependencyError("cycle detected")

    def test_catch_key_conflict_error_as_eventd_error(self):
        """KeyConflictError can be caught as EventdError."""
        with pytest.raises(EventdError):
            raise KeyConflictError("key conflict")

    def test_catch_event_validation_error_as_value_error(self):
        """EventValidationError can be caught as ValueError."""
        with pytest.raises(ValueError):
            raise EventValidationError("validation failed")

    def test_catch_all_eventd_errors(self):
        """All eventd errors can be caught with single except clause."""
        errors = [
            EventValidationError("validation"),
            CyclicDependencyError("cycle"),
            KeyConflictError("conflict"),
        ]

        for error in errors:
            with pytest.raises(EventdError):
                raise error
