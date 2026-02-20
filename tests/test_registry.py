"""Tests for BaseRegistry dependency graph behavior."""

import pytest
from conftest import Ping

from affairon import Dispatcher, MutableAffair
from affairon.exceptions import CyclicDependencyError


class TestRegistry:
    @staticmethod
    def _make():
        """Return a fresh registry backed by a real Dispatcher guardian."""
        return Dispatcher()._registry

    def test_after_ordering(self):
        """after=[a] guarantees b runs after a."""
        reg = self._make()

        def a(e: MutableAffair) -> None: ...
        def b(e: MutableAffair) -> None: ...

        reg.add([Ping], a)
        reg.add([Ping], b, after=[a])

        flat = [cb for layer in reg.exec_order(Ping) for cb in layer]
        assert flat.index(a) < flat.index(b)

    def test_after_unregistered_raises(self):
        """after referencing unknown callback raises ValueError."""
        reg = self._make()

        def a(e: MutableAffair) -> None: ...
        def ghost(e: MutableAffair) -> None: ...

        with pytest.raises(ValueError):
            reg.add([Ping], a, after=[ghost])

    def test_cycle_raises(self):
        """Circular after chain raises CyclicDependencyError."""
        reg = self._make()

        def a(e: MutableAffair) -> None: ...
        def b(e: MutableAffair) -> None: ...

        reg.add([Ping], a)
        reg.add([Ping], b, after=[a])
        with pytest.raises(CyclicDependencyError):
            reg.add([Ping], a, after=[b])

    def test_remove_excludes_callback(self):
        """Removed callback no longer in exec_order."""
        reg = self._make()

        def a(e: MutableAffair) -> None: ...

        reg.add([Ping], a)
        reg.remove([Ping], a)
        flat = [cb for layer in reg.exec_order(Ping) for cb in layer]
        assert a not in flat
