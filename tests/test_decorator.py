"""Tests for on() and listen() decorators."""

from conftest import Ping, Pong

from affairon import Dispatcher, listen


def _msg_is_yes(affair: Ping) -> bool:
    return affair.msg == "yes"


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


class TestDecoratorListen:
    def test_listen_stamps_metadata(self):
        @listen(Ping, Pong)
        def multi(affair) -> None: ...

        from affairon.listen import get_listen_spec

        spec = get_listen_spec(multi)
        assert spec is not None
        assert spec.affair_types == [Ping, Pong]
        assert spec.after is None
        assert spec.when is None

    def test_listen_preserves_after_when(self):
        d = Dispatcher()

        @d.on(Ping)
        def dep(affair: Ping) -> None: ...

        @listen(Ping, after=[dep], when=_msg_is_yes)
        def handler(affair: Ping) -> None: ...

        from affairon.listen import get_listen_spec

        spec = get_listen_spec(handler)
        assert spec is not None
        assert spec.affair_types == [Ping]
        assert spec.after == [dep]
        assert spec.when is _msg_is_yes
