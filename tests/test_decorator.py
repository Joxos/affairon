"""Tests for on() decorator — method detection and metadata stamping."""

from affairon import AffairAware, Dispatcher
from conftest import Ping, Pong


# =============================================================================
# Method vs function detection
# =============================================================================


class TestDecoratorMethodDetection:
    def test_plain_function_registered_immediately(self):
        """Plain function (no 'self' param) is registered at decoration time."""
        d = Dispatcher()

        @d.on(Ping)
        def handler(affair: Ping) -> dict[str, str]:
            return {"ok": affair.msg}

        # Callable immediately — no AffairAware needed
        result = d.emit(Ping(msg="x"))
        assert result == {"ok": "x"}

    def test_method_defers_registration(self):
        """Method (first param 'self') defers — only metadata stamped,
        registered only after instantiation."""
        d = Dispatcher()

        class Handler(AffairAware):
            @d.on(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"handled": affair.msg}

        # Before instantiation: metadata present but not in registry
        func = Handler.__dict__["handle"]
        assert hasattr(func, "_affair_types")
        assert func._affair_types == [Ping]
        assert func._affair_dispatcher is d
        assert d.emit(Ping(msg="x")) == {}

        # After instantiation: registered
        Handler()
        assert d.emit(Ping(msg="x")) == {"handled": "x"}


# =============================================================================
# Metadata stamping
# =============================================================================


class TestDecoratorMetadataStamping:
    def test_metadata_stamping(self):
        """Decorator stamps _affair_types, _affair_after, and
        _affair_dispatcher on the raw function object."""
        d = Dispatcher()

        @d.on(Ping)
        def dep(affair: Ping) -> None: ...

        class H(AffairAware):
            @d.on(Ping, Pong)
            def multi(self, affair) -> None: ...

            @d.on(Ping, after=[dep])
            def with_after(self, affair: Ping) -> None: ...

            @d.on(Ping)
            def no_after(self, affair: Ping) -> None: ...

        # Multiple affair types
        multi_fn = H.__dict__["multi"]
        assert multi_fn._affair_types == [Ping, Pong]
        assert multi_fn._affair_dispatcher is d

        # after list preserved
        with_after_fn = H.__dict__["with_after"]
        assert with_after_fn._affair_after == [dep]

        # after=None when omitted
        no_after_fn = H.__dict__["no_after"]
        assert no_after_fn._affair_after is None
