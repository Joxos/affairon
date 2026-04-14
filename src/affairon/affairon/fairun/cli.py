"""CLI entry point for fairun.

Parses the project path from command-line arguments, discovers
``pyproject.toml``, selects dispatcher mode, composes plugins on that
dispatcher, and emits ``AffairMain``.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import cast

from loguru import logger

from affairon import AffairMain, default_async_dispatcher, default_dispatcher
from affairon.aware import DispatcherLike
from affairon.composer import PluginComposer
from affairon.fairun.stubgen import generate_stub_files

log = logger.bind(source=__name__)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="fairun",
        description="Run an affairon application from its project directory.",
    )
    _ = parser.add_argument(
        "project_path",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Path to the project directory containing pyproject.toml "
        + "(defaults to current directory).",
    )
    _ = parser.add_argument(
        "--async",
        dest="use_async",
        action="store_true",
        default=False,
        help="Use the async dispatcher to emit AffairMain.",
    )
    _ = parser.add_argument(
        "--stub",
        dest="generate_stubs",
        action="store_true",
        default=False,
        help="Generate .pyi stub files for node tree attribute declarations.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: discover pyproject, compose plugins, emit AffairMain.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    project_path: Path = cast(Path, args.project_path).resolve()

    if not project_path.is_dir():
        log.error("Not a directory: {}", project_path)
        sys.exit(1)

    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.is_file():
        log.error("No pyproject.toml found in {}", project_path)
        sys.exit(1)

    use_async = bool(cast(bool, args.use_async))
    generate_stubs = bool(cast(bool, args.generate_stubs))

    if use_async:
        dispatcher = default_async_dispatcher
        composer = PluginComposer(cast(DispatcherLike, cast(object, dispatcher)))
        composer.compose_from_pyproject(pyproject_path)

        if generate_stubs:
            generated_files = generate_stub_files(project_path)
            print(f"Generated {len(generated_files)} stub file(s).")
            for file_path in generated_files:
                print(file_path)
            return

        affair = AffairMain(project_path=project_path, dispatcher=dispatcher)
        log.info("Starting application (async) from {}", project_path)
        _ = asyncio.run(dispatcher.emit(affair))
    else:
        dispatcher = default_dispatcher
        composer = PluginComposer(cast(DispatcherLike, cast(object, dispatcher)))
        composer.compose_from_pyproject(pyproject_path)

        if generate_stubs:
            generated_files = generate_stub_files(project_path)
            print(f"Generated {len(generated_files)} stub file(s).")
            for file_path in generated_files:
                print(file_path)
            return

        affair = AffairMain(project_path=project_path, dispatcher=dispatcher)
        log.info("Starting application from {}", project_path)
        _ = dispatcher.emit(affair)
