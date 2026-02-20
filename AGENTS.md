# AGENTS.md — Affairon

Affair-driven framework for Python. Affairs are Pydantic models emitted through dispatchers;
callbacks register via decorators, return `dict | None`, and results are merged.

## Build & Run Commands

Package manager: **uv** (with `uv.lock`). Always use `uv run` to execute tools.

```bash
# Install dependencies (includes dev group)
uv sync

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_dispatcher.py

# Run a single test by node ID
uv run pytest tests/test_dispatcher.py::TestSyncDispatcher::test_emit_single_listener

# Run tests matching a keyword
uv run pytest -k "test_after_ordering"

# Run tests verbose
uv run pytest -v

# Lint
uv run ruff check .

# Lint with auto-fix
uv run ruff check --fix .

# Format check
uv run ruff format --check .

# Format (apply)
uv run ruff format .
```

## Project Structure

```
affairon/              # Main package
  __init__.py          # Public API, re-exports, default_dispatcher singleton
  _types.py            # PEP 695 type aliases (SyncCallback, AsyncCallback)
  affairs.py           # Affair/MutableAffair (Pydantic) data models
  aware.py             # AffairAware mixin + AffairAwareMeta metaclass
  base_dispatcher.py   # Abstract BaseDispatcher with on()/on_method()/register()/unregister()
  dispatcher.py        # Sync Dispatcher (emit executes layers sequentially)
  async_dispatcher.py  # AsyncDispatcher (same-layer callbacks run concurrently)
  registry.py          # BaseRegistry — NetworkX dependency graph, exec_order()
  composer.py          # PluginComposer — entry point + local plugin loading
  exceptions.py        # Exception hierarchy (all inherit AffairError)
  utils.py             # merge_dict helper
  fairun/              # CLI runner subpackage
    cli.py             # argparse entry point, composes plugins, emits AffairMain
tests/
  conftest.py          # Shared test affair types: Ping, Pong, MutablePing
  test_*.py            # Test modules, one per source module
examples/              # Example plugin projects
```

## Python Version

Requires **Python >= 3.12**. Uses modern syntax throughout:
- PEP 695 `type` statement for type aliases (`type StandardResult[V] = ...`)
- PEP 695 generic classes (`class BaseRegistry[CB]:`, `class BaseDispatcher[CB]:`)
- `except*` (ExceptionGroup handling) in async_dispatcher
- `collections.abc` imports for `Callable`, `Coroutine`

## Code Style

### Ruff Configuration

Line length: **88**. Target: **py312**.

Enabled rule sets: `E` (pycodestyle errors), `W` (pycodestyle warnings), `F` (pyflakes),
`I` (isort), `N` (pep8-naming), `UP` (pyupgrade), `B` (flake8-bugbear).

isort known-first-party: `["affairon"]`.

### Import Order

Follow isort convention (enforced by ruff `I` rules):

```python
# 1. stdlib
import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from typing import Any

# 2. third-party
import networkx as nx
from loguru import logger
from pydantic import BaseModel, ConfigDict

# 3. first-party (affairon)
from affairon.affairs import MutableAffair
from affairon.exceptions import CyclicDependencyError
```

- Use `from` imports for specific names; bare `import` for namespace usage (`import networkx as nx`)
- Prefer `collections.abc` over `typing` for `Callable`, `Coroutine`, etc.
- Never use wildcard imports

### Naming Conventions

- **Modules**: `snake_case.py` (e.g., `base_dispatcher.py`, `async_dispatcher.py`)
- **Classes**: `PascalCase` (e.g., `BaseDispatcher`, `MutableAffair`, `PluginComposer`)
- **Functions/methods**: `snake_case` (e.g., `exec_order`, `merge_dict`, `compose_from_pyproject`)
- **Constants**: `UPPER_SNAKE_CASE` (e.g., `ENTRY_POINT_GROUP`)
- **Private attributes**: `_single_underscore` prefix (e.g., `_guardian`, `_registry`, `_graphs`)
- **Internal modules**: `_underscore` prefix (e.g., `_types.py`)
- **Type aliases**: `PascalCase` via `type` statement (e.g., `type SyncCallback = ...`)

### Type Annotations

- **All** function signatures must have full type annotations (params + return)
- Use PEP 695 `type` statement for type aliases (not `TypeAlias`)
- Use PEP 695 generic syntax for generic classes (`class Foo[T]:`)
- Use `X | Y` union syntax (not `Union[X, Y]`)
- Use `list[...]`, `dict[...]`, `set[...]` (lowercase builtins, not `typing.List`)
- `Any` from `typing` is acceptable for truly dynamic values
- Never suppress type errors with `# type: ignore` unless necessary for dynamic attribute stamping
  (the codebase uses `# type: ignore[attr-defined]` only in `on_method()` for metaprogramming)

### Docstrings

Google-style with sections. Every module, class, and public method has a docstring.

```python
def emit(self, affair: MutableAffair) -> dict[str, Any]:
    """Synchronously dispatch affair.

    Args:
        affair: MutableAffair to dispatch.

    Returns:
        Merged dict of all listener results.

    Raises:
        TypeError: If listener returns non-dict value.
        KeyConflictError: If merging dicts causes key conflict.
    """
```

Module docstrings are short, one-paragraph descriptions at file top.
Class docstrings describe purpose; include `Attributes:` section when fields are non-obvious.

### Error Handling

- All custom exceptions inherit from `AffairError` (base exception in `exceptions.py`)
- Wrap external errors into framework-specific types (e.g., `ValidationError` -> `AffairValidationError`)
- Use `raise X from exc` to chain exceptions
- Specific exception subclasses for each error domain: `PluginNotFoundError`, `PluginVersionError`, `PluginImportError`, etc.
- Never use bare `except:` — always catch specific types
- Logging uses `loguru` with `logger.bind(source="...")` for module-scoped loggers

### Class Patterns

- Pydantic `BaseModel` subclasses for data (affairs). Use `ConfigDict(frozen=True)` for immutability.
- ABC for abstract base classes (e.g., `BaseDispatcher`)
- Metaclass (`AffairAwareMeta`) for automatic callback registration
- Generic classes with PEP 695 syntax (`class BaseDispatcher[CB](ABC):`)

## Testing Conventions

Framework: **pytest** with **pytest-asyncio** (`asyncio_mode = "auto"`).

- Test files: `test_<module>.py` — mirror source modules
- Test classes: `Test<Feature>` — group related tests (e.g., `TestSyncDispatcher`, `TestRegistry`)
- Test functions: `test_<behavior>` — descriptive names (e.g., `test_emit_key_conflict`)
- Each test has a one-line docstring explaining the assertion
- Shared fixtures/types in `tests/conftest.py` (Ping, Pong, MutablePing affairs)
- Use `pytest.raises(ExceptionType)` for expected errors
- Create fresh `Dispatcher()` instances per test (no shared state)
- Async tests: `@pytest.mark.asyncio` decorator + `async def`
- No mocking — tests use real dispatcher/registry instances
