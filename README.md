# Affairon

An affair-driven framework oriented around "requirement seams": expose requirements as **affair hook points**, allowing multiple callbacks to collaborate on a single seam and merge results.

---

## Positioning & Philosophy

Traditional extension often means "write new code + modify existing code."
Affairon's stance: treat a requirement as an affair hook point; callbacks that implement the affair's functionality attach like **plugins**. Calling the seam (an **affair call**) is like calling a **large extensible function**:

- Multiple callbacks collaborate on the same seam
- Callback results are merged and returned
- **affair-as-contract**

---

## Core Features

- **Type safety**: affairs are Pydantic models
- **Evolvable**: affair classes support inheritance
- **Controllable order**: `after` declares execution order; the framework can generate layered plans via multiple strategies
- **Naturally concurrent**: once required order is controlled, other tasks on the seam are naturally concurrent
- **Result aggregation**: multiple callbacks return dicts that are merged
- **Plugin system**: discover and load plugins via Python entry points and `pyproject.toml`
- **CLI runner (`fairun`)**: read project configuration, compose plugins, and start the application from the command line

---

## Quick Start

### Installation

```bash
pip install affairon
# or with uv
uv add affairon
```

### Define an Affair

```python
from affairon import Affair, MutableAffair

class AddIngredients(Affair):
    """Immutable affair — listeners read fields but cannot modify them."""
    ingredients: tuple[str, ...]

class PrepCondiments(MutableAffair):
    """Mutable affair — listeners can modify fields in-place."""
    condiments: dict[str, int]
```

### Register Callbacks

```python
from affairon import default_dispatcher as dispatcher

@dispatcher.on(AddIngredients)
def extra_ingredients(affair: AddIngredients) -> dict[str, list[str]]:
    return {"extras": ["salt", "pepper"]}
```

### Emit an Affair

```python
result = dispatcher.emit(AddIngredients(ingredients=("egg",)))
# result == {"extras": ["salt", "pepper"]}
```

---

## Plugin System

Affairon supports two kinds of plugins, both declared in `pyproject.toml`:

### External Plugins (Entry Points)

External packages register via the `affairon.plugins` entry point group.
The host application lists them under `[tool.affairon] plugins` using PEP 508 requirement strings:

```toml
# Host's pyproject.toml
[tool.affairon]
plugins = ["my-plugin>=1.0"]
```

```toml
# Plugin's pyproject.toml
[project.entry-points."affairon.plugins"]
my-plugin = "my_plugin.lib"
```

### Local Plugins (Direct Import)

Modules within the host application itself can be declared via `local_plugins`.
They are imported directly, triggering callback registration through decorators:

```toml
[tool.affairon]
local_plugins = ["myapp.lib", "myapp.host"]
```

**Load order**: external plugins first, local plugins second.

---

## CLI Runner — `fairun`

`fairun` is a built-in CLI that reads `pyproject.toml`, composes all plugins, and emits an `AffairMain` affair to start the application:

```bash
fairun /path/to/project
# or, from the project directory:
fairun
```

Applications define their entry point by listening on `AffairMain`:

```python
from affairon import AffairMain, default_dispatcher as dispatcher

@dispatcher.on(AffairMain)
def main(affair: AffairMain) -> None:
    print(f"Running from {affair.project_path}")
```

---

## Class-Based Handlers — `AffairAware`

For class-based callback organization, inherit from `AffairAware`.
Decorated methods are automatically registered as bound callbacks when the class is instantiated — no `super().__init__()` call required:

```python
from affairon import AffairAware, Dispatcher

d = Dispatcher()

class Kitchen(AffairAware):
    def __init__(self, chef: str):
        self.chef = chef

    @d.on(AddIngredients)
    def cook(self, affair: AddIngredients) -> dict[str, str]:
        return {"chef": self.chef}

k = Kitchen("Alice")  # cook() is now a registered bound method
result = d.emit(AddIngredients(ingredients=("egg",)))
# result == {"chef": "Alice"}
```

The `AffairAwareMeta` metaclass handles registration after `__init__` completes, so subclasses work transparently without any boilerplate.

---

## Design Tradeoffs

This paradigm is not "universal," but its gains and costs are both clear:

**Gains**

- Clearer architecture: seam as contract
- Safer extension: affair types are traceable, refactorable, and verifiable
- More controllable execution: explicit order / concurrency

**Costs / Risks**

- Debugging needs stronger trace visibility
- Composition and extension increase maintenance cost (versioning, compatibility, testing)
- Abstraction introduces performance overhead (mitigate via hot-path consolidation)

Affairon's long-term goal: reduce costs and risks via framework assistance (affair stack, conflict detection, evolving policies).

---

## Key Semantics

- **Callback returns**: returning a `dict` is merged; returning `None` contributes nothing
- **Conflicts**: key collisions raise `KeyConflictError`
- **Dependency order**: `after` declares "must run before" callbacks
- **Async concurrency**: same-layer callbacks run concurrently; failures may surface as `ExceptionGroup`

---

## Project Vision

If you align with this paradigm, contributions and discussions are welcome.
