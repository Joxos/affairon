import importlib
import importlib.metadata
import inspect
import tomllib
from pathlib import Path
from typing import Any

from loguru import logger
from packaging.requirements import Requirement
from packaging.version import Version

from affairon.exceptions import (
    PluginEntryPointError,
    PluginImportError,
    PluginNotFoundError,
    PluginTargetError,
    PluginVersionError,
)
from affairon.listen import get_listen_spec
from affairon.utils import normalize_name

log = logger.bind(source=__name__)

ENTRY_POINT_GROUP = "affairon.plugins"


def _validate_listener_mode(dispatcher: Any, callback: Any) -> None:
    dispatcher_is_async = inspect.iscoroutinefunction(dispatcher.emit)
    callback_is_async = inspect.iscoroutinefunction(callback)

    if dispatcher_is_async == callback_is_async:
        return

    expected = "async" if dispatcher_is_async else "sync"
    actual = "async" if callback_is_async else "sync"
    raise PluginTargetError(
        f"{callback.__qualname__} is {actual}, but {type(dispatcher).__qualname__} "
        f"requires {expected} callbacks"
    )


class PluginComposer:
    def __init__(self, dispatcher: Any) -> None:
        self.dispatcher = dispatcher
        self.loaded_plugins: set[str] = set()
        self.loaded_local_plugins: set[str] = set()

    def compose(self, plugin_requirements: list[str]) -> None:
        for req_str in plugin_requirements:
            requirement = Requirement(req_str)
            self._load_plugin(requirement)

    def compose_local(self, modules: list[str]) -> None:
        for module_path in modules:
            if module_path in self.loaded_local_plugins:
                log.debug("Local plugin already loaded: {}", module_path)
                continue

            self._load_local_module(module_path)
            self.loaded_local_plugins.add(module_path)
            log.info("Local plugin '{}' loaded", module_path)

    def compose_from_pyproject(self, pyproject_path: Path) -> None:
        with open(pyproject_path, "rb") as fh:
            config = tomllib.load(fh)

        affairon_config = config.get("tool", {}).get("affairon", {})
        plugin_reqs: list[str] = affairon_config.get("plugins", [])
        local_plugins: list[str] = affairon_config.get("local_plugins", [])

        if not plugin_reqs and not local_plugins:
            log.info("No plugins declared in {}", pyproject_path)
            return

        if local_plugins:
            self.compose_local(local_plugins)

        if plugin_reqs:
            self.compose(plugin_reqs)

    def _load_plugin(self, requirement: Requirement) -> None:
        plugin_name = requirement.name
        normalized_name = normalize_name(plugin_name)

        if normalized_name in self.loaded_plugins:
            log.debug("Plugin already loaded: {}", plugin_name)
            return

        try:
            dist = importlib.metadata.distribution(plugin_name)
        except importlib.metadata.PackageNotFoundError as err:
            raise PluginNotFoundError(
                f"Required plugin '{plugin_name}' is not installed"
            ) from err

        installed_version = Version(dist.version)
        if not requirement.specifier.contains(installed_version):
            raise PluginVersionError(
                f"Plugin '{plugin_name}' version {installed_version} "
                f"does not satisfy requirement '{requirement}'"
            )

        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP, name=plugin_name)
        if not eps:
            raise PluginEntryPointError(
                f"Plugin '{plugin_name}' has no entry point "
                f"in group '{ENTRY_POINT_GROUP}'"
            )

        ep = next(iter(eps))
        module_path = ep.value.split(":", 1)[0]
        self._import_and_register_module(module_path, plugin_label=plugin_name)

        self.loaded_plugins.add(normalized_name)
        log.info("Plugin '{}' v{} loaded", plugin_name, installed_version)

    def _load_local_module(self, module_path: str) -> None:
        if ":" in module_path:
            raise PluginTargetError(
                f"Local plugin target '{module_path}' must be a module path"
            )
        self._import_and_register_module(module_path, plugin_label=module_path)

    def _import_and_register_module(
        self, module_path: str, *, plugin_label: str
    ) -> None:
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:
            log.exception("Failed to import plugin module '{}'", module_path)
            raise PluginImportError(
                f"Failed to import plugin module '{module_path}': {exc}"
            ) from exc

        self._register_module_listeners(module, plugin_label=plugin_label)

    def _register_module_listeners(self, module: Any, *, plugin_label: str) -> None:
        module_callbacks: dict[Any, Any] = {}
        callback_specs: list[tuple[Any, Any]] = []
        registrations: list[tuple[list[Any], Any]] = []

        for _name, attr in vars(module).items():
            if not callable(attr):
                continue
            if getattr(attr, "__module__", None) != module.__name__:
                continue
            spec = get_listen_spec(attr)
            if spec is None:
                continue
            module_callbacks[attr] = attr
            callback_specs.append((attr, spec))

        try:
            for callback, spec in callback_specs:
                _validate_listener_mode(self.dispatcher, callback)
                after = spec.after
                if after:
                    after = [module_callbacks.get(cb, cb) for cb in after]
                self.dispatcher.register(
                    spec.affair_types,
                    callback,
                    after=after,
                    when=spec.when,
                )
                registrations.append((spec.affair_types, callback))
        except Exception as exc:
            for affair_types, callback in registrations:
                try:
                    self.dispatcher.unregister(*affair_types, callback=callback)
                except Exception:
                    pass
            if isinstance(exc, PluginTargetError):
                raise
            raise PluginTargetError(
                f"Failed to register listened callbacks from '{plugin_label}'"
            ) from exc

        log.debug(
            "Registered {} listened callback(s) from module '{}'",
            len(callback_specs),
            plugin_label,
        )
