# eventd

A flexible event-driven framework for Python supporting both sync and async modes.

## Features

- Type-safe event definitions using Pydantic
- Synchronous and asynchronous dispatch modes
- Priority-based and dependency-based listener ordering
- MRO-aware event inheritance
- Zero external runtime dependencies (except pydantic and loguru)

## Requirements

- Python 3.12+
- pydantic >= 2.0
- loguru >= 0.7

## Installation

```bash
pip install eventd
```

## Development

```bash
uv pip install -e ".[dev]"
pytest
```
