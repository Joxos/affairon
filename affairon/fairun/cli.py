"""CLI entry point for fairun.

Parses the project path from command-line arguments, discovers
``pyproject.toml``, composes plugins, and emits ``AffairMain``.
"""

import argparse
import sys
from pathlib import Path

from loguru import logger

from affairon import default_dispatcher
from affairon.affairs import AffairMain
from affairon.composer import PluginComposer

fairun_logger = logger.bind(source="fairun")


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="fairun",
        description="Run an affairon application from its project directory.",
    )
    parser.add_argument(
        "project_path",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Path to the project directory containing pyproject.toml "
        "(defaults to current directory).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: discover pyproject, compose plugins, emit AffairMain.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    project_path: Path = args.project_path.resolve()

    if not project_path.is_dir():
        fairun_logger.error(f"Not a directory: {project_path}")
        sys.exit(1)

    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.is_file():
        fairun_logger.error(f"No pyproject.toml found in {project_path}")
        sys.exit(1)

    # Compose plugins from pyproject.toml
    composer = PluginComposer()
    composer.compose_from_pyproject(pyproject_path)

    fairun_logger.info(f"Starting application from {project_path}")

    # Emit AffairMain to kick off the application
    default_dispatcher.emit(AffairMain(project_path=project_path))
