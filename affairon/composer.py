"""Plugin composer for affairon.

Discovers and loads plugins using the Python entry point mechanism.
Plugin packages declare entry points in the ``affairon`` group; host
applications list required plugins (with optional version constraints)
in ``[tool.affairon]`` of their ``pyproject.toml``.

Local plugins (modules within the host application itself) can also be
declared via the ``local_plugins`` key and are loaded by direct import.

Typical usage::

    from affairon.composer import PluginComposer

    composer = PluginComposer()
    composer.compose_from_pyproject(Path("pyproject.toml"))
"""

import importlib
import importlib.metadata
import tomllib
from pathlib import Path

from loguru import logger
from packaging.requirements import Requirement
from packaging.version import Version

from affairon.exceptions import (
    PluginEntryPointError,
    PluginNotFoundError,
    PluginVersionError,
)

composer_logger = logger.bind(source="affairon_plugin_composer")

ENTRY_POINT_GROUP = "affairon.plugins"


class PluginComposer:
    """Discover and load affairon plugins via entry points.

    Plugins register themselves by declaring an entry point in the
    ``affairon`` group.  The entry point value should be a dotted module
    path whose import triggers callback registration (e.g. via
    ``@dispatcher.on(...)`` decorators).

    Host applications specify which plugins to load using PEP 508
    requirement strings, either programmatically or via
    ``[tool.affairon]`` in their ``pyproject.toml``.

    Local plugins (dotted module paths) are loaded via direct import,
    bypassing the entry point and version check mechanisms.
    """

    def __init__(self) -> None:
        self.loaded_plugins: set[str] = set()
        self.loaded_local_plugins: set[str] = set()

    # -- public API -----------------------------------------------------------

    def compose(self, plugin_requirements: list[str]) -> None:
        """Load plugins matching the given requirement strings.

        For each requirement string the method:

        1. Parses the PEP 508 specifier.
        2. Verifies the package is installed and satisfies the version
           constraint.
        3. Finds the package's ``affairon`` entry point.
        4. Imports the entry point module, which triggers callback
           registration.

        Args:
            plugin_requirements: PEP 508 requirement strings,
                e.g. ``["eggsample-spam>0.1.0"]``.

        Raises:
            PluginNotFoundError: If a required plugin is not installed.
            PluginVersionError: If the installed version does not satisfy
                the requirement.
            PluginEntryPointError: If the plugin declares no entry point
                in the ``affairon`` group.
        """
        for req_str in plugin_requirements:
            requirement = Requirement(req_str)
            self._load_plugin(requirement)

    def compose_local(self, module_paths: list[str]) -> None:
        """Load local plugins by importing dotted module paths.

        Each module path is imported directly via ``importlib.import_module``.
        The import triggers callback registration through decorators.

        Args:
            module_paths: Dotted module paths, e.g. ``["eggsample.lib"]``.
        """
        for module_path in module_paths:
            if module_path in self.loaded_local_plugins:
                composer_logger.debug(f"Local plugin already loaded: {module_path}")
                continue

            try:
                composer_logger.debug(f"Loading local plugin '{module_path}'")
                importlib.import_module(module_path)
                self.loaded_local_plugins.add(module_path)
                composer_logger.info(f"Local plugin '{module_path}' loaded")
            except Exception as exc:
                composer_logger.exception(
                    f"Failed to load local plugin '{module_path}': {exc}"
                )
                raise

    def compose_from_pyproject(self, pyproject_path: Path) -> None:
        """Load plugins declared in a ``pyproject.toml`` file.

        Reads the ``[tool.affairon]`` table and loads:

        1. ``plugins`` — external plugins via entry points (first).
        2. ``local_plugins`` — local modules via direct import (second).

        Args:
            pyproject_path: Path to the ``pyproject.toml`` file.
        """
        with open(pyproject_path, "rb") as fh:
            config = tomllib.load(fh)

        affairon_config = config.get("tool", {}).get("affairon", {})
        plugin_reqs: list[str] = affairon_config.get("plugins", [])
        local_plugins: list[str] = affairon_config.get("local_plugins", [])

        if not plugin_reqs and not local_plugins:
            composer_logger.info(f"No plugins declared in {pyproject_path}")
            return

        # External plugins first
        if plugin_reqs:
            self.compose(plugin_reqs)

        # Local plugins second (can override/extend external behavior)
        if local_plugins:
            self.compose_local(local_plugins)

    # -- internals ------------------------------------------------------------

    def _load_plugin(self, requirement: Requirement) -> None:
        """Resolve, validate, and import a single plugin.

        Args:
            requirement: Parsed PEP 508 requirement.
        """
        plugin_name = requirement.name

        if plugin_name in self.loaded_plugins:
            composer_logger.debug(f"Plugin already loaded: {plugin_name}")
            return

        # 1. Check installation
        try:
            dist = importlib.metadata.distribution(plugin_name)
        except importlib.metadata.PackageNotFoundError as err:
            raise PluginNotFoundError(
                f"Required plugin '{plugin_name}' is not installed"
            ) from err

        # 2. Check version constraint
        installed_version = Version(dist.version)
        if not requirement.specifier.contains(installed_version):
            raise PluginVersionError(
                f"Plugin '{plugin_name}' version {installed_version} "
                f"does not satisfy requirement '{requirement}'"
            )

        # 3. Find entry point
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP, name=plugin_name)
        if not eps:
            raise PluginEntryPointError(
                f"Plugin '{plugin_name}' has no entry point "
                f"in group '{ENTRY_POINT_GROUP}'"
            )

        ep = next(iter(eps))

        # 4. Import the entry point module (triggers decorator registration)
        try:
            composer_logger.debug(f"Loading plugin '{plugin_name}' from {ep.value}")
            ep.load()
            self.loaded_plugins.add(plugin_name)
            composer_logger.info(f"Plugin '{plugin_name}' v{installed_version} loaded")
        except Exception as exc:
            composer_logger.exception(f"Failed to load plugin '{plugin_name}': {exc}")
            raise
