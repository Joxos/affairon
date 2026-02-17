"""Core tests for affairon — 15 cases covering all essential behaviors."""

import pytest
from pydantic import ValidationError

from affairon import (
    MutableAffair,
    Affair,
    AffairValidationError,
    Dispatcher,
    KeyConflictError,
)
from affairon.async_dispatcher import AsyncDispatcher
from affairon.exceptions import CyclicDependencyError

# -- shared fixtures ----------------------------------------------------------


class Ping(Affair):
    msg: str


class Pong(Affair):
    msg: str


# -- 1. Affair model -----------------------------------------------------------


class TestAffair:
    def test_custom_fields(self):
        """1.1 — user-defined fields work."""
        e = Ping(msg="hi")
        assert e.msg == "hi"

    def test_validation_wraps_pydantic(self):
        """1.3 — missing required field → AffairValidationError."""
        with pytest.raises(AffairValidationError):
            Ping()  # type: ignore[call-arg]
        with pytest.raises(AffairValidationError):
            Ping(msg=1)  # type: ignore[call-arg]

    def test_frozen(self):
        """1.4 — Affair instances are immutable."""
        e = Ping(msg="hi")
        with pytest.raises(ValidationError):
            e.msg = "bye"  # type: ignore[misc]


# -- 2. Registry (dependency graph) -------------------------------------------


class TestRegistry:
    @staticmethod
    def _make():
        """Return a registry backed by a real Dispatcher guardian."""
        return Dispatcher()._registry

    def test_after_ordering(self):
        """2.6 — after=[a] guarantees b runs after a."""
        reg = self._make()

        def a(e: MutableAffair) -> None: ...
        def b(e: MutableAffair) -> None: ...

        reg.add([Ping], a)
        reg.add([Ping], b, after=[a])

        flat = [cb for layer in reg.exec_order(Ping) for cb in layer]
        assert flat.index(a) < flat.index(b)

    def test_after_unregistered_raises(self):
        """2.7 — after referencing unknown callback → ValueError."""
        reg = self._make()

        def a(e: MutableAffair) -> None: ...
        def ghost(e: MutableAffair) -> None: ...

        with pytest.raises(ValueError):
            reg.add([Ping], a, after=[ghost])

    def test_cycle_raises(self):
        """2.8 — circular after chain → CyclicDependencyError."""
        reg = self._make()

        def a(e: MutableAffair) -> None: ...
        def b(e: MutableAffair) -> None: ...

        reg.add([Ping], a)
        reg.add([Ping], b, after=[a])
        with pytest.raises(CyclicDependencyError):
            reg.add([Ping], a, after=[b])

    def test_remove_excludes_callback(self):
        """2.9 — removed callback no longer in exec_order."""
        reg = self._make()

        def a(e: MutableAffair) -> None: ...

        reg.add([Ping], a)
        reg.remove([Ping], a)
        flat = [cb for layer in reg.exec_order(Ping) for cb in layer]
        assert a not in flat


# -- 3. Sync Dispatcher -------------------------------------------------------


class TestSyncDispatcher:
    def test_emit_single_listener(self):
        """3.11 — single listener returns dict via emit."""
        d = Dispatcher()
        d.register(Ping, lambda e: {"ok": True})
        assert d.emit(Ping(msg="x")) == {"ok": True}

    def test_emit_key_conflict(self):
        """3.12 — overlapping keys → KeyConflictError."""
        d = Dispatcher()
        d.register(Ping, lambda e: {"k": 1})
        d.register(Ping, lambda e: {"k": 2})
        with pytest.raises(KeyConflictError):
            d.emit(Ping(msg="x"))

    def test_on_decorator_end_to_end(self):
        """3.13 — @on() registers and emit invokes callback."""
        d = Dispatcher()
        called = []

        @d.on(Ping)
        def handler(e: MutableAffair) -> None:
            called.append(e)

        d.emit(Ping(msg="hi"))
        assert len(called) == 1


# -- 4. Async Dispatcher ------------------------------------------------------


class TestAsyncDispatcher:
    @pytest.mark.asyncio
    async def test_emit_merges_results(self):
        """4.15 — multiple async listeners, results merged."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def h1(e: MutableAffair) -> dict:
            return {"a": 1}

        @d.on(Ping)
        async def h2(e: MutableAffair) -> dict:
            return {"b": 2}

        result = await d.emit(Ping(msg="x"))
        assert result == {"a": 1, "b": 2}

    @pytest.mark.asyncio
    async def test_emit_exception_group(self):
        """4.16 — failing listeners → ExceptionGroup propagated."""
        d = AsyncDispatcher()

        @d.on(Ping)
        async def bad1(e: MutableAffair) -> dict:
            raise ValueError("e1")

        @d.on(Ping)
        async def bad2(e: MutableAffair) -> dict:
            raise ValueError("e2")

        with pytest.raises(ExceptionGroup) as exc_info:
            await d.emit(Ping(msg="x"))
        assert len(exc_info.value.exceptions) == 2


# -- 5. Unregister ------------------------------------------------------------


class TestUnregister:
    def test_mode1_specific_callback_specific_affair(self):
        """5.17 — unregister(Affair, callback=cb) removes only that pair."""
        d = Dispatcher()

        def h(e: MutableAffair) -> None: ...

        d.register(Ping, h)
        d.unregister(Ping, callback=h)
        assert d.emit(Ping(msg="x")) == {}

    def test_mode2_all_listeners_from_affair(self):
        """5.18 — unregister(Affair) clears all listeners for that affair."""
        d = Dispatcher()
        d.register(Ping, lambda e: {"a": 1})
        d.register(Ping, lambda e: {"b": 2})
        d.unregister(Ping)
        assert d.emit(Ping(msg="x")) == {}

    def test_mode3_callback_from_all_affairs(self):
        """5.19 — unregister(callback=cb) removes it everywhere."""
        d = Dispatcher()

        def h(e: MutableAffair) -> None: ...

        d.register([Ping, Pong], h)
        d.unregister(callback=h)
        assert d.emit(Ping(msg="x")) == {}
        assert d.emit(Pong(msg="x")) == {}
