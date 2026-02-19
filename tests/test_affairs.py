"""Tests for Affair / MutableAffair model behavior."""

import pytest
from pydantic import ValidationError

from affairon import AffairValidationError
from conftest import MutablePing, Ping


class TestAffair:
    def test_custom_fields(self):
        """User-defined fields are accessible."""
        e = Ping(msg="hi")
        assert e.msg == "hi"

    def test_validation_wraps_pydantic(self):
        """Missing/wrong fields raise AffairValidationError."""
        with pytest.raises(AffairValidationError):
            Ping()  # type: ignore[call-arg]
        with pytest.raises(AffairValidationError):
            Ping(msg=1)  # type: ignore[call-arg]

    def test_frozen(self):
        """Affair instances are immutable."""
        e = Ping(msg="hi")
        with pytest.raises(ValidationError):
            e.msg = "bye"  # type: ignore[misc]
