"""CLI entry point for fairun.

Parses the project path from command-line arguments, discovers
``pyproject.toml``, composes plugins, and emits ``AffairMain``.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from affairon import AffairMain, default_async_dispatcher, default_dispatcher
from affairon.composer import PluginComposer

log = logger.bind(source=__name__)


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
    parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        default=False,
        help="Use the async dispatcher to emit AffairMain.",
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
        log.error("Not a directory: {}", project_path)
        sys.exit(1)

    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.is_file():
        log.error("No pyproject.toml found in {}", project_path)
        sys.exit(1)

    # Compose plugins from pyproject.toml
    composer = PluginComposer()
    composer.compose_from_pyproject(pyproject_path)

    affair = AffairMain(project_path=project_path)

    if args.use_async:
        log.info("Starting application (async) from {}", project_path)
        asyncio.run(default_async_dispatcher.emit(affair))
    else:
        log.info("Starting application from {}", project_path)
        default_dispatcher.emit(affair)
