"""Plugin composer for affairon.

Discovers and loads plugins using the Python entry point mechanism.
Plugin packages declare entry points in the ``affairon`` group; host
applications list required plugins (with optional version constraints)
in ``[tool.affairon]`` of their ``pyproject.toml``.

Typical usage::

    from affairon.composer import PluginComposer

    composer = PluginComposer()
    composer.compose(["eggsample-spam>0.1.0"])

Or load from a ``pyproject.toml``::

    composer.compose_from_pyproject(Path("pyproject.toml"))
"""

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
    """

    def __init__(self) -> None:
        self.loaded_plugins: set[str] = set()

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

    def compose_from_pyproject(self, pyproject_path: Path) -> None:
        """Load plugins declared in a ``pyproject.toml`` file.

        Reads the ``[tool.affairon]`` table and extracts the ``plugins``
        list, then delegates to :meth:`compose`.

        Args:
            pyproject_path: Path to the ``pyproject.toml`` file.
        """
        with open(pyproject_path, "rb") as fh:
            config = tomllib.load(fh)

        plugin_reqs: list[str] = (
            config.get("tool", {}).get("affairon", {}).get("plugins", [])
        )

        if not plugin_reqs:
            composer_logger.info(f"No plugins declared in {pyproject_path}")
            return

        self.compose(plugin_reqs)

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
