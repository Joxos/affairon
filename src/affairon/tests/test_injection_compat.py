from types import SimpleNamespace
from typing import cast

from affairon import AffairAware, Dispatcher, inject_from, listen
from affairon.affairs import MutableAffair
from affairon.composer import PluginComposer
from affairon.listen import get_listen_spec


class Ping(MutableAffair):
    msg: str
    injector: object | None = None


class Pong(MutableAffair):
    msg: str


class RuntimeA:
    def __init__(self, value: str) -> None:
        self.value = value


class Injector:
    def __init__(self) -> None:
        self._values: dict[type[object], object] = {RuntimeA: RuntimeA("ok")}

    def inject(self, key: type[RuntimeA]) -> RuntimeA:
        value = self._values.get(key)
        if value is None:
            raise LookupError(f"{key.__name__} not provided")
        return cast(RuntimeA, value)


def test_listen_metadata_survives_injection_wrapper() -> None:
    @listen(Ping, Pong)
    @inject_from(lambda affair: affair.injector)
    def listener(affair: Ping, runtime: RuntimeA) -> dict[str, str]:
        return {"value": runtime.value}

    spec = get_listen_spec(listener)

    assert spec is not None
    assert spec.affair_types == [Ping, Pong]


def test_composer_registers_wrapped_listener() -> None:
    dispatcher = Dispatcher()
    composer = PluginComposer(dispatcher)

    @listen(Ping)
    @inject_from(lambda affair: affair.injector)
    def local_listener(affair: Ping, runtime: RuntimeA) -> dict[str, str]:
        return {"value": runtime.value}

    local_listener.__module__ = "plugin.local"
    module = SimpleNamespace(__name__="plugin.local", local_listener=local_listener)

    import affairon.composer as composer_module

    original_import_module = composer_module.importlib.import_module
    composer_module.importlib.import_module = lambda _name: module
    try:
        composer.compose_local(["plugin.local"])
    finally:
        composer_module.importlib.import_module = original_import_module

    affair = Ping(msg="x", injector=Injector())
    assert dispatcher.emit(affair) == {"value": "ok"}


def test_affair_aware_binds_wrapped_method() -> None:
    dispatcher = Dispatcher()

    class Handler(AffairAware):
        def __init__(self, injector: Injector) -> None:
            self.injector = injector

        @listen(Ping)
        @inject_from(lambda self, affair: self.injector)
        def handle(self, affair: Ping, runtime: RuntimeA) -> dict[str, str]:
            return {"value": runtime.value}

    Handler(Injector(), dispatcher=dispatcher)
    assert dispatcher.emit(Ping(msg="x")) == {"value": "ok"}
