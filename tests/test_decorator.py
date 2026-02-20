"""Tests for on() and on_method() decorators."""

from conftest import Ping, Pong

from affairon import AffairAware, Dispatcher

# =============================================================================
# on() — plain function immediate registration
# =============================================================================


class TestDecoratorOn:
    def test_plain_function_registered_immediately(self):
        """Plain function is registered at decoration time via on()."""
        d = Dispatcher()

        @d.on(Ping)
        def handler(affair: Ping) -> dict[str, str]:
            return {"ok": affair.msg}

        # Callable immediately — no AffairAware needed
        result = d.emit(Ping(msg="x"))
        assert result == {"ok": "x"}


# =============================================================================
# on_method() — deferred registration for class methods
# =============================================================================


class TestDecoratorOnMethod:
    def test_method_defers_registration(self):
        """on_method() only stamps metadata; registration happens at instantiation."""
        d = Dispatcher()

        class Handler(AffairAware):
            @d.on_method(Ping)
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

    def test_metadata_stamping(self):
        """on_method() stamps _affair_types, _affair_after, and
        _affair_dispatcher on the raw function object."""
        d = Dispatcher()

        @d.on(Ping)
        def dep(affair: Ping) -> None: ...

        class H(AffairAware):
            @d.on_method(Ping, Pong)
            def multi(self, affair) -> None: ...

            @d.on_method(Ping, after=[dep])
            def with_after(self, affair: Ping) -> None: ...

            @d.on_method(Ping)
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
