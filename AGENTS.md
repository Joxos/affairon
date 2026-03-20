# AGENTS.md - Affairon

Affairon is a Python framework built around affair dispatch. Affairs are
Pydantic models, callbacks register on dispatchers, callbacks return
`dict | None`, and dispatcher output is the merged result.

No repo-local Cursor rules (`.cursor/rules/`, `.cursorrules`) or Copilot rules
(`.github/copilot-instructions.md`) are present in this repository. Treat this
file as the main guide for coding agents working here.

## Baseline

- Python `>=3.12`
- Package manager and task runner: `uv`
- Lint and formatting: `ruff`
- Tests: `pytest` and `pytest-asyncio`
- Type checking: `pyright`
- Packaging backend: `hatchling`

This repo is disciplined. Follow existing patterns closely, keep diffs small,
and preserve public behavior unless the task explicitly changes semantics.

## Verified commands

Run project tools through `uv`.

```bash
# Install runtime and dev dependencies
uv sync

# Run the full test suite
uv run pytest

# Run one test file
uv run pytest tests/test_dispatcher.py

# Run one test by node id
uv run pytest tests/test_dispatcher.py::TestSyncDispatcher::test_emit_single_listener

# Run tests by keyword
uv run pytest -k "test_after_ordering"

# Lint
uv run ruff check .

# Lint and auto-fix
uv run ruff check --fix .

# Format check / apply
uv run ruff format --check .
uv run ruff format .

# Type check
uv run pyright
```

There is no repo-specific build command beyond standard Python packaging.
Validate most changes with targeted tests, `ruff`, and `pyright`.

## Repository map

- `affairon/__init__.py`: public exports, default dispatcher singletons,
  `logger.disable("affairon")`
- `affairon/affairs.py`: `Affair`, `MutableAffair`, meta-affairs, merge strategy
- `affairon/_types.py`: shared callback type aliases
- `affairon/listen.py`: delayed-binding metadata for `@listen`
- `affairon/dispatcher.py` and `async_dispatcher.py`: sync and async dispatch
- `affairon/registry.py`: dependency graph, ordering, and `when=` filtering
- `affairon/aware.py`: `AffairAware` binding and cleanup
- `affairon/composer.py`: plugin discovery, import, and auto-registration
- `affairon/fairun/cli.py`: `fairun` CLI entry point
- `tests/`: pytest suite covering sync, async, registry, composer, and aware
- `examples/`: example plugin projects used by tests and docs

## Semantics agents must preserve

- `Affair` is immutable and forbids extra fields.
- `MutableAffair` is mutable, validates assignment, and also forbids extra
  fields.
- Pydantic `ValidationError` is wrapped as `AffairValidationError`.
- Callback contract is `dict | None`. Returning `None` means no contribution.
- Default merge behavior is `raise`; supported strategies are `raise`, `keep`,
  `override`, `list_merge`, and `dict_merge`.
- `emit_up=False` dispatches only the concrete affair type.
- `emit_up=True` walks the affair type MRO child-first and also fires callbacks
  registered on parent affair types.
- Cross-hierarchy key conflicts still raise `KeyConflictError` under the
  default merge strategy.
- `on()` registers plain functions immediately.
- `listen()` stores metadata and does not register immediately.
- `AffairAware` registers bound `@listen` methods after instance creation using
  the dispatcher passed at instantiation, even if subclasses skip
  `super().__init__()`.
- `AffairAware` supports explicit `unregister()` cleanup and context-manager
  lifetime.
- `after=[callback]` defines dependency order. Unknown dependencies and cycles
  are validated by the registry.
- `when=` predicates are stored in the registry and checked at emit time.
- `AsyncDispatcher` runs same-layer callbacks concurrently with
  `asyncio.TaskGroup`; async failures may surface as `ExceptionGroup`.
- Callback failures are routed through `CallbackErrorAffair`.
- Error-policy keys are `retry`, `deadletter`, and `silent`.
- Error-affair dispatch intentionally uses `raise` semantics so policy dicts are
  not wrapped by list or dict merge strategies.
- Plugin load order matters: local plugins first, external entry-point plugins
  second.
- External plugins are discovered from the `affairon.plugins` entry-point group.
- Local plugins must be module paths, not `module:symbol` targets.
- Composer only auto-registers callbacks defined in the scanned module; it
  ignores imported callbacks.
- `fairun` selects sync or async dispatcher first, composes plugins onto that
  dispatcher, then emits `AffairMain` on the same dispatcher.

## Style and typing conventions

- Group imports as stdlib, third-party, then first-party.
- Treat `affairon` as the first-party package for import sorting.
- Prefer `collections.abc` for `Callable`, `Coroutine`, and similar protocols.
- Use `snake_case` for modules, functions, and methods, `PascalCase` for
  classes and type aliases, and `UPPER_SNAKE_CASE` for constants.
- Fully annotate function signatures.
- Prefer modern typing with builtin generics (`list[...]`, `dict[...]`) and
  `X | Y` unions.
- This codebase already uses Python 3.12 features, including PEP 695 `type`
  aliases and generic syntax. Match that when editing related code.
- Keep runtime behavior type-safe. Avoid `Any` unless it is already justified by
  framework boundaries or metaprogramming.
- Avoid `# type: ignore` unless it is narrowly scoped and genuinely necessary.
- Ruff lint rules enabled in `pyproject.toml` are `E`, `W`, `F`, `I`, `N`,
  `UP`, and `B`.
- Ruff uses the default 88-character line length unless repo config changes.
- Keep module docstrings short where they exist.
- Public classes and methods generally use concise Google-style docstrings.
- Runtime modules commonly bind Loguru once at module scope with
  `log = logger.bind(source=__name__)`.
- Affairon logging is disabled by default in `affairon/__init__.py`; enable it
  with `logger.enable("affairon")` when debugging.
- Use Loguru `{}` formatting instead of f-strings in logging calls.
- Prefer helper functions like `callable_name()` when logging callback names.

## Error-handling conventions

- Framework exceptions inherit from `AffairError`.
- Wrap external failures with `raise ... from exc`.
- Do not introduce bare `except:` blocks.
- Do not swallow broad exceptions unless you are matching an existing cleanup or
  retry path that clearly requires it.
- If you touch callback error handling, preserve the current retry -> deadletter
  -> silent -> re-raise behavior.

## Testing conventions

- Test files are named `test_<module>.py`.
- Test classes use names like `TestSyncDispatcher` and `TestRegistry`.
- Tests usually have short one-line docstrings.
- Shared affair types for tests live in `tests/conftest.py`.
- Prefer fresh `Dispatcher()` or `AsyncDispatcher()` instances per test.
- The suite favors real framework objects over mocks.
- When behavior changes, add or update focused tests near the affected module.
- If you change dispatch semantics, inspect tests covering `emit_up`, `when`,
  `after`, merge strategies, plugin loading, and async error handling.

## Practical workflow for agents

1. Read the affected module and its matching tests first.
2. Preserve existing public semantics unless the task says otherwise.
3. Make the smallest change that solves the problem.
4. Run the narrowest useful test first, then broader validation.
5. Preferred validation order:
   - related test file or node id
   - `uv run ruff check .`
   - `uv run ruff format --check .`
   - `uv run pyright`
   - `uv run pytest`
6. If a broader command fails because of a pre-existing issue, call that out
   separately instead of folding it into your change.
