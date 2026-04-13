from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from conftest import Ping

from affairon import Dispatcher, listen
from affairon.composer import PluginComposer
from affairon.exceptions import PluginConfigError, PluginTargetError


def _unregistered_dependency(affair):
    return {"dependency": affair.msg}


class TestPluginComposer:
    def test_external_entry_point_imports_module_and_registers_listeners(
        self, monkeypatch
    ):
        dispatcher = Dispatcher()
        composer = PluginComposer(dispatcher)

        @listen(Ping)
        def external_listener(affair):
            return {"ok": "ext"}

        external_listener.__module__ = "fake_plugin.lib"

        module = SimpleNamespace(
            __name__="fake_plugin.lib", external_listener=external_listener
        )
        dist = SimpleNamespace(version="1.2.0")
        ep = SimpleNamespace(value="fake_plugin.lib:any_symbol")

        monkeypatch.setattr(
            "affairon.composer.importlib.metadata.distribution",
            lambda _name: dist,
        )
        monkeypatch.setattr(
            "affairon.composer.importlib.metadata.entry_points",
            lambda **_kwargs: [ep],
        )
        monkeypatch.setattr(
            "affairon.composer.importlib.import_module",
            lambda _name: module,
        )

        captured: list[tuple[Any, Any, Any, Any]] = []
        original_register = dispatcher.register

        def spy_register(affair_types, callback, *, after=None, when=None):
            captured.append((affair_types, callback, after, when))
            return original_register(affair_types, callback, after=after, when=when)

        monkeypatch.setattr(dispatcher, "register", spy_register)

        composer.compose(["fake-plugin>=1.0"])

        assert len(captured) == 1
        affair_types, callback, after, when = captured[0]
        assert affair_types == [Ping]
        assert callback is external_listener
        assert after is None
        assert when is None

    def test_local_plugin_target_must_be_module_path(self):
        composer = PluginComposer(Dispatcher())

        with pytest.raises(PluginTargetError, match="module path"):
            composer.compose_local(["eggsample.lib:listen"])

    def test_compose_from_pyproject_loads_local_then_external(
        self,
        monkeypatch,
        tmp_path: Path,
    ):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "\n".join(
                [
                    "[tool.affairon]",
                    'plugins = ["ext>=1.0"]',
                    'local_plugins = ["app.lib", "app.host"]',
                ]
            ),
            encoding="utf-8",
        )

        composer = PluginComposer(Dispatcher())
        events: list[str] = []

        monkeypatch.setattr(
            composer, "compose", lambda reqs: events.append(f"ext:{reqs}")
        )
        monkeypatch.setattr(
            composer,
            "compose_local",
            lambda targets: events.append(f"local:{targets}"),
        )

        composer.compose_from_pyproject(pyproject)

        assert events == [
            "local:['app.lib', 'app.host']",
            "ext:['ext>=1.0']",
        ]

    def test_compose_from_pyproject_profile_loads_local_then_external(
        self,
        monkeypatch,
        tmp_path: Path,
    ):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "\n".join(
                [
                    "[tool.affairon]",
                    'local_plugins = ["app.main"]',
                    "",
                    "[tool.affairon.profiles.kernel]",
                    'plugins = ["ext>=2.0"]',
                    'local_plugins = ["kernel.bridge", "kernel.host"]',
                ]
            ),
            encoding="utf-8",
        )

        composer = PluginComposer(Dispatcher())
        events: list[str] = []

        monkeypatch.setattr(
            composer, "compose", lambda reqs: events.append(f"ext:{reqs}")
        )
        monkeypatch.setattr(
            composer,
            "compose_local",
            lambda targets: events.append(f"local:{targets}"),
        )

        composer.compose_from_pyproject(pyproject, profile="kernel")

        assert events == [
            "local:['kernel.bridge', 'kernel.host']",
            "ext:['ext>=2.0']",
        ]

    def test_compose_from_pyproject_raises_for_missing_profile(
        self,
        tmp_path: Path,
    ):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[tool.affairon]\n", encoding="utf-8")

        composer = PluginComposer(Dispatcher())

        with pytest.raises(PluginConfigError, match="Profile 'kernel' not found"):
            composer.compose_from_pyproject(pyproject, profile="kernel")

    @pytest.mark.parametrize(
        ("config_line", "match"),
        [
            ('plugins = "ext>=1.0"', "plugins"),
            ('local_plugins = ["kernel.host", 1]', "local_plugins"),
        ],
    )
    def test_compose_from_pyproject_raises_for_invalid_profile_plugin_lists(
        self,
        tmp_path: Path,
        config_line: str,
        match: str,
    ):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "\n".join(
                [
                    "[tool.affairon.profiles.kernel]",
                    config_line,
                ]
            ),
            encoding="utf-8",
        )

        composer = PluginComposer(Dispatcher())

        with pytest.raises(PluginConfigError, match=match):
            composer.compose_from_pyproject(pyproject, profile="kernel")

    def test_compose_from_pyproject_raises_for_invalid_toml(self, tmp_path: Path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[tool.affairon\n", encoding="utf-8")

        composer = PluginComposer(Dispatcher())

        with pytest.raises(PluginConfigError, match="Failed to parse pyproject"):
            composer.compose_from_pyproject(pyproject)

    def test_compose_from_pyproject_empty_profile_is_noop(
        self,
        monkeypatch,
        tmp_path: Path,
    ):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            "\n".join(
                [
                    "[tool.affairon.profiles.kernel]",
                ]
            ),
            encoding="utf-8",
        )

        composer = PluginComposer(Dispatcher())
        events: list[str] = []

        monkeypatch.setattr(
            composer, "compose", lambda reqs: events.append(f"ext:{reqs}")
        )
        monkeypatch.setattr(
            composer,
            "compose_local",
            lambda targets: events.append(f"local:{targets}"),
        )

        composer.compose_from_pyproject(pyproject, profile="kernel")

        assert events == []

    def test_only_module_defined_functions_are_auto_registered(self, monkeypatch):
        dispatcher = Dispatcher()
        composer = PluginComposer(dispatcher)

        @listen(Ping)
        def imported_callback(affair):
            return {"source": "imported"}

        imported_callback.__module__ = "other.module"

        @listen(Ping)
        def local_callback(affair):
            return {"source": "local"}

        local_callback.__module__ = "plugin.local"

        module = SimpleNamespace(
            __name__="plugin.local",
            imported_callback=imported_callback,
            local_callback=local_callback,
        )

        monkeypatch.setattr(
            "affairon.composer.importlib.import_module",
            lambda _name: module,
        )

        registered: list[Any] = []
        original_register = dispatcher.register

        def spy_register(affair_types, callback, *, after=None, when=None):
            registered.append(callback)
            return original_register(affair_types, callback, after=after, when=when)

        monkeypatch.setattr(dispatcher, "register", spy_register)

        composer.compose_local(["plugin.local"])

        assert registered == [local_callback]

    def test_sync_dispatcher_rejects_async_listeners(self, monkeypatch):
        dispatcher = Dispatcher()
        composer = PluginComposer(dispatcher)

        @listen(Ping)
        async def async_callback(affair):
            return {"bad": affair.msg}

        async_callback.__module__ = "plugin.async_mod"

        module = SimpleNamespace(
            __name__="plugin.async_mod", async_callback=async_callback
        )

        monkeypatch.setattr(
            "affairon.composer.importlib.import_module",
            lambda _name: module,
        )

        with pytest.raises(PluginTargetError, match="requires sync callbacks"):
            composer.compose_local(["plugin.async_mod"])

    def test_failed_module_registration_rolls_back(self, monkeypatch):
        dispatcher = Dispatcher()
        composer = PluginComposer(dispatcher)

        @listen(Ping)
        def first(affair):
            return {"first": affair.msg}

        first.__module__ = "plugin.rollback"

        @listen(Ping, after=[_unregistered_dependency])
        def second(affair):
            return {"second": affair.msg}

        second.__module__ = "plugin.rollback"

        module = SimpleNamespace(__name__="plugin.rollback", first=first, second=second)

        monkeypatch.setattr(
            "affairon.composer.importlib.import_module",
            lambda _name: module,
        )

        with pytest.raises(PluginTargetError, match="Failed to register"):
            composer.compose_local(["plugin.rollback"])

        assert dispatcher.emit(Ping(msg="x")) == {}
