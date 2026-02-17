import importlib
from pathlib import Path

from loguru import logger

module_logger = logger.bind(source="moduvent_module_loader")


class ModuleLoader:
    _skip_prefixes = ("__", ".")

    def __init__(self) -> None:
        self.loaded_modules: set[str] = set()

    def discover_modules(self, path: Path) -> None:
        """Discover and load modules from given path.

        Uses pkgutil.walk_packages to discover importable modules under the
        target path and imports them by name.
        """
        if not isinstance(path, Path):
            raise TypeError("path must be a pathlib.Path instance")

        # check if the path exists
        if not path.exists():
            raise FileNotFoundError(f"Module directory does not exist: {path}")

        # check if the path is a directory
        if not path.is_dir():
            raise NotADirectoryError(f"Module path is not a directory: {path}")

        # recursively discover modules

    def load_module(self, module_name: str) -> None:
        """Load a module by name."""
        module_name = module_name.strip(".")
        if not module_name:
            return
        if module_name in self.loaded_modules:
            module_logger.debug(f"Module already loaded: {module_name}")
            return

        try:
            module_logger.debug(f"Attempting to import: {module_name}")
            importlib.import_module(module_name)
            self.loaded_modules.add(module_name)
            module_logger.debug(f"{module_name} successfully loaded.")
        except ImportError as e:
            module_logger.exception(f"Error loading module {module_name}: {e}")
        except Exception as ex:
            module_logger.exception(f"Unexpected error loading {module_name}: {ex}")
