# AGENTS.md - Seamverse

Seamverse is a uv workspace centered on the Affairon Python package.

- `src/affairon/`: the Affairon package and its docs, tests, and examples

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

## Workspace commands

Run project tools through `uv` from the workspace root.

```bash
# Install workspace dependencies
uv sync

# Run Affairon tests
uv run pytest

# Lint
uv run ruff check .

# Format check
uv run ruff format --check .

# Type check
uv run pyright

# Run the Affairon CLI
uv run --package affairon fairun --help
```

## Repository map

- `src/affairon/pyproject.toml`: Affairon package metadata
- `src/affairon/affairon/`: Affairon source package
- `src/affairon/tests/`: Affairon test suite
- `src/affairon/examples/`: Affairon example projects

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

## Current node DSL boundaries

- Plain `@listen` callbacks remain explicit and non-injecting.
- `@associate(...)` methods may receive injected node-local or locator-resolved parameters.
- Non-local node lookup must be expressed through locators such as `Annotated[T, Root / A / T]`.
