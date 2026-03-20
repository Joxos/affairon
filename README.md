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

Affairon provides two global dispatcher singletons: `default_dispatcher` (sync)
and `default_async_dispatcher` (async). We recommend importing with an alias
for brevity:

```python
# Sync
from affairon import default_dispatcher as dispatcher

# Async
from affairon import default_async_dispatcher as dispatcher
```

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

## Plugin system

Affairon supports two plugin sources, both declared in `pyproject.toml`:

### External plugins (entry points)

External packages register in the `affairon.plugins` entry point group.
The entry point target can be any symbol in the plugin module; affairon imports
the module and auto-registers module-level callbacks decorated with `@listen`.

The host application lists packages under `[tool.affairon] plugins` using PEP 508 requirement strings:

```toml
# Host's pyproject.toml
[tool.affairon]
plugins = ["my-plugin>=1.0"]
```

```toml
# Plugin's pyproject.toml
[project.entry-points."affairon.plugins"]
my-plugin = "my_plugin.lib:any_symbol"
```

### Local plugins (module import)

Modules within the host application itself can be declared via `local_plugins`.
Each item must be a module path:

```toml
[tool.affairon]
local_plugins = ["myapp.lib", "myapp.host"]
```

At compose time affairon imports each module and auto-registers only callbacks
defined in that module (imported callbacks are ignored to avoid duplicate registration).

**Load order**: local plugins first, external plugins second. This lets host
callbacks exist before external extensions reference them with `after=[...]`.

---

## CLI Runner — `fairun`

`fairun` is a built-in CLI that reads `pyproject.toml`, selects the dispatcher,
composes all plugins on that dispatcher, and emits `AffairMain` on the same dispatcher:

```bash
fairun /path/to/project
# or, from the project directory:
fairun
```

Use `--async` to emit via the async dispatcher instead:

```bash
fairun --async /path/to/project
```

Applications define their entry point by listening on `AffairMain`:

```python
from affairon import AffairMain
from affairon.listen import listen

@listen(AffairMain)
def main(affair: AffairMain) -> None:
    print(f"Running from {affair.project_path}")
# affair.dispatcher is the selected dispatcher instance.
```

---

## Class-based handlers - `AffairAware`

For class-based callback organization, inherit from `AffairAware`.
Use `@listen` on class methods and pass `dispatcher=` at instantiation.
Bound callbacks are registered automatically after `__init__` completes, and
`super().__init__()` is still not required:

```python
from affairon import AffairAware, Dispatcher
from affairon.listen import listen

d = Dispatcher()

class Kitchen(AffairAware):
    def __init__(self, chef: str):
        self.chef = chef

    @listen(AddIngredients)
    def cook(self, affair: AddIngredients) -> dict[str, str]:
        return {"chef": self.chef}

k = Kitchen("Alice", dispatcher=d)  # cook() is now registered as a bound method
result = d.emit(AddIngredients(ingredients=("egg",)))
# result == {"chef": "Alice"}
```

- `on()` — registers a plain function immediately
- `listen()` — stamps delayed-binding metadata for module-level callbacks and class methods

`@staticmethod` and `@classmethod` are supported - place them **outside** `@listen()`:

```python
class Handler(AffairAware):
    @staticmethod
    @listen(Ping)
    def static_handle(affair: Ping) -> dict[str, str]:
        return {"static": "yes"}

    @classmethod
    @listen(Ping)
    def class_handle(cls, affair: Ping) -> dict[str, str]:
        return {"cls": cls.__name__}
```

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
- **Affair propagation (`emit_up`)**: `MutableAffair` has an `emit_up: bool = False` field.
  When `True`, `emit()` walks the affair type's MRO (child-first) and also invokes callbacks
  registered on parent affair types.  Cross-hierarchy key conflicts raise `KeyConflictError`.

---

## Logging

Affairon uses [loguru](https://github.com/Delgan/loguru) internally.
**All logging is disabled by default** — no output will appear unless
you explicitly enable it:

```python
from loguru import logger

# Enable affairon logs (sent to loguru's default stderr sink)
logger.enable("affairon")
```

To disable again:

```python
logger.disable("affairon")
```

Because affairon delegates to loguru, you control the output format,
level filtering, and sinks entirely through loguru's configuration:

```python
import sys
from loguru import logger

# Remove default sink, add your own
logger.remove()
logger.add(sys.stderr, level="DEBUG", filter="affairon")

logger.enable("affairon")
```

---

## Project Vision

If you align with this paradigm, contributions and discussions are welcome.
