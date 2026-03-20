import pytest
from conftest import Ping

from affairon import AffairAware, AsyncDispatcher, Dispatcher, listen
from affairon.affairs import MutableAffair


def _yes_msg(affair: MutableAffair) -> bool:
    return isinstance(affair, Ping) and affair.msg == "yes"


def _not_skip_msg(affair: MutableAffair) -> bool:
    return isinstance(affair, Ping) and affair.msg != "skip"


def _go_msg(affair: MutableAffair) -> bool:
    return isinstance(affair, Ping) and affair.msg == "go"


def _unregistered_dependency(affair: Ping) -> dict[str, str]:
    return {"dependency": affair.msg}


class TestAffairAwareBasic:
    def test_registration_lifecycle(self):
        d = Dispatcher()

        class Handler(AffairAware):
            def __init__(self, tag: str):
                self.tag = tag

            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {self.tag: affair.msg}

        assert d.emit(Ping(msg="x")) == {}

        Handler("mytag", dispatcher=d)
        result = d.emit(Ping(msg="hi"))
        assert result == {"mytag": "hi"}

    def test_no_registration_edge_cases(self):
        d = Dispatcher()

        class Empty(AffairAware):
            pass

        Empty()
        assert d.emit(Ping(msg="x")) == {}

        class SkippedSuper(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"ok": affair.msg}

            def __init__(self):
                pass

        SkippedSuper(dispatcher=d)
        assert d.emit(Ping(msg="x")) == {"ok": "x"}

    def test_missing_dispatcher_raises_for_listened_methods(self):
        class Handler(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"ok": affair.msg}

        with pytest.raises(ValueError, match="requires dispatcher"):
            Handler()

    def test_binding_rolls_back_when_later_registration_fails(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping)
            def first(self, affair: Ping) -> dict[str, str]:
                return {"first": affair.msg}

            @listen(Ping, after=[_unregistered_dependency])
            def second(self, affair: Ping) -> dict[str, str]:
                return {"second": affair.msg}

        with pytest.raises(ValueError, match="not registered"):
            Handler(dispatcher=d)

        assert d.emit(Ping(msg="x")) == {}

    def test_async_dispatcher_rejects_sync_listeners(self):
        d = AsyncDispatcher()

        class Handler(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"ok": affair.msg}

        with pytest.raises(TypeError, match="requires async callbacks"):
            Handler(dispatcher=d)


class TestAffairAwareAfterDeps:
    def test_after_between_methods(self):
        d = Dispatcher()
        order: list[str] = []

        class Handler(AffairAware):
            @listen(Ping)
            def first(self, affair: Ping) -> dict[str, int]:
                order.append("first")
                return {"first": 1}

            @listen(Ping, after=[first])
            def second(self, affair: Ping) -> dict[str, int]:
                order.append("second")
                return {"second": 2}

        Handler(dispatcher=d)
        result = d.emit(Ping(msg="x"))
        assert order == ["first", "second"]
        assert result == {"first": 1, "second": 2}

    def test_after_mixing_plain_function_and_method(self):
        d = Dispatcher()
        order: list[str] = []

        @d.on(Ping)
        def plain(affair: Ping) -> dict[str, int]:
            order.append("plain")
            return {"plain": 1}

        class Handler(AffairAware):
            @listen(Ping, after=[plain])
            def method(self, affair: Ping) -> dict[str, int]:
                order.append("method")
                return {"method": 2}

        Handler(dispatcher=d)
        result = d.emit(Ping(msg="x"))
        assert order == ["plain", "method"]
        assert result == {"plain": 1, "method": 2}


class TestAffairAwareInheritance:
    def test_subclass_override_replaces_base(self):
        d = Dispatcher()

        class Base(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"who": "base"}

        class Child(Base):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"who": "child"}

        Child(dispatcher=d)
        result = d.emit(Ping(msg="x"))
        assert result == {"who": "child"}

    def test_multiple_instances_separate_registrations(self):
        d = Dispatcher()

        class Handler(AffairAware):
            def __init__(self, name: str):
                self.name = name

            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {self.name: affair.msg}

        Handler("h1", dispatcher=d)
        Handler("h2", dispatcher=d)
        result = d.emit(Ping(msg="hi"))
        assert result == {"h1": "hi", "h2": "hi"}


class TestAffairAwareStaticAndClassMethod:
    def test_staticmethod_registered_on_instantiation(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @staticmethod
            @listen(Ping)
            def handle(affair: Ping) -> dict[str, str]:
                return {"static": affair.msg}

        assert d.emit(Ping(msg="x")) == {}

        Handler(dispatcher=d)
        result = d.emit(Ping(msg="hello"))
        assert result == {"static": "hello"}

    def test_classmethod_registered_on_instantiation(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @classmethod
            @listen(Ping)
            def handle(cls, affair: Ping) -> dict[str, str]:
                return {"cls": cls.__name__}

        assert d.emit(Ping(msg="x")) == {}

        Handler(dispatcher=d)
        result = d.emit(Ping(msg="x"))
        assert result == {"cls": "Handler"}

    def test_mixed_instance_static_classmethod(self):
        d = Dispatcher()

        class Handler(AffairAware):
            def __init__(self, tag: str):
                self.tag = tag

            @listen(Ping)
            def instance_handle(self, affair: Ping) -> dict[str, str]:
                return {"instance": self.tag}

            @staticmethod
            @listen(Ping)
            def static_handle(affair: Ping) -> dict[str, str]:
                return {"static": "yes"}

            @classmethod
            @listen(Ping)
            def class_handle(cls, affair: Ping) -> dict[str, str]:
                return {"class": cls.__name__}

        Handler("mytag", dispatcher=d)
        result = d.emit(Ping(msg="x"))
        assert result == {"instance": "mytag", "static": "yes", "class": "Handler"}


class TestAffairAwareUnregister:
    def test_unregister_removes_all_callbacks(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"h": affair.msg}

        h = Handler(dispatcher=d)
        assert d.emit(Ping(msg="x")) == {"h": "x"}

        h.unregister()
        assert d.emit(Ping(msg="x")) == {}

    def test_unregister_idempotent(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"ok": "yes"}

        h = Handler(dispatcher=d)
        h.unregister()
        h.unregister()
        assert d.emit(Ping(msg="x")) == {}

    def test_unregister_preserves_other_registrations(self):
        d = Dispatcher()

        @d.on(Ping)
        def permanent(affair: Ping) -> dict[str, str]:
            return {"permanent": "yes"}

        class Handler(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"temp": "yes"}

        h = Handler(dispatcher=d)
        assert d.emit(Ping(msg="x")) == {"permanent": "yes", "temp": "yes"}

        h.unregister()
        assert d.emit(Ping(msg="x")) == {"permanent": "yes"}


class TestAffairAwareContextManager:
    def test_callbacks_unregistered_on_exit(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"ctx": affair.msg}

        with Handler(dispatcher=d):
            assert d.emit(Ping(msg="hi")) == {"ctx": "hi"}

        assert d.emit(Ping(msg="hi")) == {}

    def test_multiple_methods_all_unregistered(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping)
            def first(self, affair: Ping) -> dict[str, str]:
                return {"a": "1"}

            @listen(Ping)
            def second(self, affair: Ping) -> dict[str, str]:
                return {"b": "2"}

        with Handler(dispatcher=d):
            assert d.emit(Ping(msg="x")) == {"a": "1", "b": "2"}

        assert d.emit(Ping(msg="x")) == {}

    def test_other_registrations_survive(self):
        d = Dispatcher()

        @d.on(Ping)
        def permanent(affair: Ping) -> dict[str, str]:
            return {"permanent": "yes"}

        class Handler(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"temp": "yes"}

        with Handler(dispatcher=d):
            result = d.emit(Ping(msg="x"))
            assert result == {"permanent": "yes", "temp": "yes"}

        assert d.emit(Ping(msg="x")) == {"permanent": "yes"}

    def test_enter_returns_instance(self):
        d = Dispatcher()

        class Handler(AffairAware):
            def __init__(self, tag: str):
                self.tag = tag

            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"tag": self.tag}

        with Handler("hello", dispatcher=d) as h:
            assert isinstance(h, Handler)
            assert h.tag == "hello"
            assert d.emit(Ping(msg="x")) == {"tag": "hello"}

    def test_exit_on_exception(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"ok": "yes"}

        try:
            with Handler(dispatcher=d):
                assert d.emit(Ping(msg="x")) == {"ok": "yes"}
                raise RuntimeError("boom")
        except RuntimeError:
            pass

        assert d.emit(Ping(msg="x")) == {}


class TestAffairAwareWhenFilter:
    def test_listen_when_true_fires(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping, when=_yes_msg)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"fired": affair.msg}

        Handler(dispatcher=d)
        assert d.emit(Ping(msg="yes")) == {"fired": "yes"}

    def test_listen_when_false_skips(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping, when=_yes_msg)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"fired": affair.msg}

        Handler(dispatcher=d)
        assert d.emit(Ping(msg="no")) == {}

    def test_listen_when_with_instance_state(self):
        d = Dispatcher()

        class Handler(AffairAware):
            def __init__(self, tag: str):
                self.tag = tag

            @listen(Ping, when=_not_skip_msg)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {self.tag: affair.msg}

        Handler("h1", dispatcher=d)
        assert d.emit(Ping(msg="hello")) == {"h1": "hello"}
        assert d.emit(Ping(msg="skip")) == {}

    def test_listen_when_context_manager(self):
        d = Dispatcher()

        class Handler(AffairAware):
            @listen(Ping, when=_go_msg)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"ok": "yes"}

        with Handler(dispatcher=d):
            assert d.emit(Ping(msg="go")) == {"ok": "yes"}
            assert d.emit(Ping(msg="stop")) == {}

        assert d.emit(Ping(msg="go")) == {}
