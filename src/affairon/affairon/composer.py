import importlib
import importlib.metadata
import tomllib
from collections.abc import Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import cast

from loguru import logger
from packaging.requirements import Requirement
from packaging.version import Version

from affairon._types import AsyncCallback, SyncCallback
from affairon.affairs import MutableAffair
from affairon.aware import DispatcherLike, validate_listener_mode
from affairon.exceptions import (
    PluginConfigError,
    PluginEntryPointError,
    PluginImportError,
    PluginNotFoundError,
    PluginTargetError,
    PluginVersionError,
)
from affairon.listen import ListenSpec, get_listen_spec
from affairon.utils import normalize_name

log = logger.bind(source=__name__)

ENTRY_POINT_GROUP = "affairon.plugins"

type TomlTable = dict[str, object]


def _config_section_name(profile: str | None) -> str:
    if profile is None:
        return "[tool.affairon]"
    return f"[tool.affairon.profiles.{profile}]"


class PluginComposer:
    def __init__(self, dispatcher: DispatcherLike) -> None:
        self.dispatcher: DispatcherLike = dispatcher
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

    def compose_from_pyproject(
        self, pyproject_path: Path, profile: str | None = None
    ) -> None:
        try:
            with pyproject_path.open("rb") as fh:
                config = cast(dict[str, object], tomllib.load(fh))
        except tomllib.TOMLDecodeError as err:
            raise PluginConfigError(
                f"Failed to parse pyproject.toml '{pyproject_path}': {err}"
            ) from err

        affairon_config = self._resolve_affairon_config(
            config,
            pyproject_path=pyproject_path,
            profile=profile,
        )
        plugin_reqs = self._read_plugin_list(
            affairon_config,
            key="plugins",
            pyproject_path=pyproject_path,
            profile=profile,
        )
        local_plugins = self._read_plugin_list(
            affairon_config,
            key="local_plugins",
            pyproject_path=pyproject_path,
            profile=profile,
        )

        if not plugin_reqs and not local_plugins:
            if profile is None:
                log.info("No plugins declared in {}", pyproject_path)
            else:
                log.info(
                    "No plugins declared in {} for profile '{}'",
                    pyproject_path,
                    profile,
                )
            return

        if local_plugins:
            self.compose_local(local_plugins)

        if plugin_reqs:
            self.compose(plugin_reqs)

    def _resolve_affairon_config(
        self,
        config: dict[str, object],
        *,
        pyproject_path: Path,
        profile: str | None,
    ) -> dict[str, object]:
        tool_config: object = config.get("tool", {})
        if not isinstance(tool_config, dict):
            raise PluginConfigError(f"[tool] in '{pyproject_path}' must be a table")

        tool_table = cast(dict[str, object], tool_config)
        affairon_config: object = tool_table.get("affairon", {})
        if not isinstance(affairon_config, dict):
            raise PluginConfigError(
                f"[tool.affairon] in '{pyproject_path}' must be a table"
            )
        affairon_table = cast(dict[str, object], affairon_config)

        if profile is None:
            return affairon_table

        profiles = affairon_table.get("profiles")
        if profiles is None:
            raise PluginConfigError(
                f"Profile '{profile}' not found in '{pyproject_path}'"
            )
        if not isinstance(profiles, dict):
            raise PluginConfigError(
                f"[tool.affairon.profiles] in '{pyproject_path}' must be a table"
            )

        profile_config = cast(dict[str, object], profiles).get(profile)
        if profile_config is None:
            raise PluginConfigError(
                f"Profile '{profile}' not found in '{pyproject_path}'"
            )
        if not isinstance(profile_config, dict):
            raise PluginConfigError(
                f"{_config_section_name(profile)} in '{pyproject_path}' must be a table"
            )

        return cast(dict[str, object], profile_config)

    def _read_plugin_list(
        self,
        affairon_config: dict[str, object],
        *,
        key: str,
        pyproject_path: Path,
        profile: str | None,
    ) -> list[str]:
        value = affairon_config.get(key, [])
        if not isinstance(value, list):
            raise PluginConfigError(
                f"{_config_section_name(profile)}.{key}"
                + f" in '{pyproject_path}'"
                + " must be a list of strings"
            )
        value_items = cast(list[object], value)
        str_items: list[str] = []
        for item in value_items:
            if not isinstance(item, str):
                raise PluginConfigError(
                    f"{_config_section_name(profile)}.{key}"
                    + f" in '{pyproject_path}'"
                    + " must be a list of strings"
                )
            str_items.append(item)
        return str_items

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
                f"Plugin '{plugin_name}' version "
                + f"{installed_version} does not satisfy"
                + f" requirement '{requirement}'"
            )

        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP, name=plugin_name)
        if not eps:
            raise PluginEntryPointError(
                f"Plugin '{plugin_name}' has no entry"
                + f" point in group '{ENTRY_POINT_GROUP}'"
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

    def _register_module_listeners(
        self, module: ModuleType, *, plugin_label: str
    ) -> None:
        module_callbacks: dict[Callable[..., object], Callable[..., object]] = {}
        callback_specs: list[tuple[Callable[..., object], ListenSpec]] = []
        registrations: list[
            tuple[list[type[MutableAffair]], SyncCallback | AsyncCallback]
        ] = []

        module_namespace = cast(Mapping[str, object], vars(module))
        for _name, attr in module_namespace.items():
            attr_obj: object = attr
            if not callable(attr_obj):
                continue
            if getattr(attr_obj, "__module__", None) != module.__name__:
                continue
            spec = get_listen_spec(attr_obj)
            if spec is None:
                continue
            callback = attr_obj
            module_callbacks[callback] = callback
            callback_specs.append((callback, spec))

        try:
            for callback, spec in callback_specs:
                validate_listener_mode(self.dispatcher, callback)
                after = spec.after
                after_cbs: list[Callable[..., object]] | None = None
                if after:
                    after_cbs = [
                        module_callbacks.get(cb, cb)
                        for cb in cast(list[Callable[..., object]], after)
                    ]
                typed_callback = cast(SyncCallback | AsyncCallback, callback)
                self.dispatcher.register(
                    spec.affair_types,
                    typed_callback,
                    after=after_cbs,
                    when=spec.when,
                )
                registrations.append((spec.affair_types, typed_callback))
        except Exception as exc:
            for affair_types, callback in registrations:
                try:
                    self.dispatcher.unregister(*affair_types, callback=callback)
                except Exception:
                    pass
            if isinstance(exc, PluginTargetError):
                raise
            raise PluginTargetError(
                f"Failed to register listened callbacks from '{plugin_label}': {exc}"
            ) from exc

        log.debug(
            "Registered {} listened callback(s) from module '{}'",
            len(callback_specs),
            plugin_label,
        )
