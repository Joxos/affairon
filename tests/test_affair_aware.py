"""Tests for AffairAware mixin — class method auto-registration."""


from conftest import Ping

from affairon import AffairAware, Dispatcher

# =============================================================================
# Basic registration lifecycle
# =============================================================================


class TestAffairAwareBasic:
    def test_registration_lifecycle(self):
        """Methods are NOT registered before init, ARE registered after,
        and bound methods receive self with access to instance state."""
        d = Dispatcher()

        class Handler(AffairAware):
            def __init__(self, tag: str):
                self.tag = tag  # no super().__init__() needed

            @d.on_method(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {self.tag: affair.msg}

        # Before instantiation — nothing registered
        assert d.emit(Ping(msg="x")) == {}

        # After instantiation — bound method registered, self accessible
        Handler("mytag")
        result = d.emit(Ping(msg="hi"))
        assert result == {"mytag": "hi"}

    def test_no_registration_edge_cases(self):
        """Empty subclass is harmless no-op. Skipping super().__init__()
        still registers callbacks thanks to the metaclass."""
        d = Dispatcher()

        class Empty(AffairAware):
            pass

        Empty()
        assert d.emit(Ping(msg="x")) == {}

        class SkippedSuper(AffairAware):
            @d.on_method(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"ok": affair.msg}

            def __init__(self):
                pass  # deliberately skip super().__init__()

        SkippedSuper()
        # Metaclass guarantees registration even without super().__init__()
        assert d.emit(Ping(msg="x")) == {"ok": "x"}


# =============================================================================
# after dependencies between methods
# =============================================================================


class TestAffairAwareAfterDeps:
    def test_after_between_methods(self):
        """after=[method_a] orders method_b after method_a within same class."""
        d = Dispatcher()
        order: list[str] = []

        class Handler(AffairAware):
            @d.on_method(Ping)
            def first(self, affair: Ping) -> dict[str, int]:
                order.append("first")
                return {"first": 1}

            @d.on_method(Ping, after=[first])
            def second(self, affair: Ping) -> dict[str, int]:
                order.append("second")
                return {"second": 2}

        Handler()
        result = d.emit(Ping(msg="x"))
        assert order == ["first", "second"]
        assert result == {"first": 1, "second": 2}

    def test_after_mixing_plain_function_and_method(self):
        """Method declared after= a previously-registered plain function."""
        d = Dispatcher()
        order: list[str] = []

        @d.on(Ping)
        def plain(affair: Ping) -> dict[str, int]:
            order.append("plain")
            return {"plain": 1}

        class Handler(AffairAware):
            @d.on_method(Ping, after=[plain])
            def method(self, affair: Ping) -> dict[str, int]:
                order.append("method")
                return {"method": 2}

        Handler()
        result = d.emit(Ping(msg="x"))
        assert order == ["plain", "method"]
        assert result == {"plain": 1, "method": 2}


# =============================================================================
# Inheritance & MRO
# =============================================================================


class TestAffairAwareInheritance:
    def test_subclass_override_replaces_base(self):
        """Subclass override replaces base decorated method in registration."""
        d = Dispatcher()

        class Base(AffairAware):
            @d.on_method(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"who": "base"}

        class Child(Base):
            @d.on_method(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {"who": "child"}

        Child()
        result = d.emit(Ping(msg="x"))
        assert result == {"who": "child"}

    def test_multiple_instances_separate_registrations(self):
        """Each instance registers its own bound methods independently."""
        d = Dispatcher()

        class Handler(AffairAware):
            def __init__(self, name: str):
                self.name = name  # no super().__init__() needed

            @d.on_method(Ping)
            def handle(self, affair: Ping) -> dict[str, str]:
                return {self.name: affair.msg}

        Handler("h1")
        Handler("h2")
        result = d.emit(Ping(msg="hi"))
        assert result == {"h1": "hi", "h2": "hi"}


# =============================================================================
# staticmethod & classmethod support
# =============================================================================


class TestAffairAwareStaticAndClassMethod:
    def test_staticmethod_registered_on_instantiation(self):
        """@staticmethod + @on_method() registers the static function
        at instantiation time."""
        d = Dispatcher()

        class Handler(AffairAware):
            @staticmethod
            @d.on_method(Ping)
            def handle(affair: Ping) -> dict[str, str]:
                return {"static": affair.msg}

        # Before instantiation — not registered
        assert d.emit(Ping(msg="x")) == {}

        Handler()
        result = d.emit(Ping(msg="hello"))
        assert result == {"static": "hello"}

    def test_classmethod_registered_on_instantiation(self):
        """@classmethod + @on_method() registers a bound class method
        that receives cls at instantiation time."""
        d = Dispatcher()

        class Handler(AffairAware):
            @classmethod
            @d.on_method(Ping)
            def handle(cls, affair: Ping) -> dict[str, str]:
                return {"cls": cls.__name__}

        assert d.emit(Ping(msg="x")) == {}

        Handler()
        result = d.emit(Ping(msg="x"))
        assert result == {"cls": "Handler"}

    def test_mixed_instance_static_classmethod(self):
        """Instance method, staticmethod, and classmethod all coexist
        in a single AffairAware subclass."""
        d = Dispatcher()

        class Handler(AffairAware):
            def __init__(self, tag: str):
                self.tag = tag

            @d.on_method(Ping)
            def instance_handle(self, affair: Ping) -> dict[str, str]:
                return {"instance": self.tag}

            @staticmethod
            @d.on_method(Ping)
            def static_handle(affair: Ping) -> dict[str, str]:
                return {"static": "yes"}

            @classmethod
            @d.on_method(Ping)
            def class_handle(cls, affair: Ping) -> dict[str, str]:
                return {"class": cls.__name__}

        Handler("mytag")
        result = d.emit(Ping(msg="x"))
        assert result == {"instance": "mytag", "static": "yes", "class": "Handler"}
