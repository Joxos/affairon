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

### Profiles (named plugin groups)

Applications with multiple dispatcher instances often need different plugin
combinations for each instance. Profiles let you declare several named groups
in one `pyproject.toml` and select one at compose time.

```toml
[tool.affairon]
local_plugins = ["myapp.main"]

[tool.affairon.profiles.duel]
local_plugins = ["duel_core.mr2020"]

[tool.affairon.profiles.kernel]
local_plugins = [
  "duel_core.kernel.bridges",
  "duel_core.kernel.planners",
  "duel_core.kernel.appliers",
]
```

`PluginComposer.compose_from_pyproject(pyproject, profile=None)` selects exactly
one configuration section:

- `profile=None` (default) — reads `[tool.affairon]`, preserving existing behaviour
- `profile="kernel"` — reads only `[tool.affairon.profiles.kernel]`
- requesting a missing profile raises `PluginConfigError`

The selected section follows the same load order as the root table:
local plugins first, then external plugins. No inheritance or merging occurs
between the root section and a selected profile.

---

## Migrating from pluggy

Affairon can cover the same basic host/plugin flow as
[pluggy](https://pluggy.readthedocs.io/), but it models the seam differently.
Pluggy is centered on named hook specs and hook implementations. Affairon is
centered on typed affair objects: the seam is a Pydantic model, listeners attach
to that model, and `emit()` returns the merged output of all listeners.

If you want a concrete example, see `examples/egg/`, which rewrites pluggy's
first `eggsample` example in affairon. From `examples/egg/eggsample/`, run:

```bash
uv run fairun .
```

### Concept map

| pluggy | affairon |
| --- | --- |
| `Hookspec` | `Affair` / `MutableAffair` class |
| `@hookimpl` | `@listen(AffairClass)`, `@dispatcher.on(AffairClass)`, or an `AffairAware` method |
| `PluginManager.register(...)` | `dispatcher.register(...)` or decorator-based registration |
| `pm.hook.my_hook(...)` | `dispatcher.emit(MyAffair(...))` |
| setuptools entry-point loading | `[tool.affairon] plugins` + `affairon.plugins` entry points |
| in-process plugin modules | `[tool.affairon] local_plugins` |
| `tryfirst` / `trylast` | `after=[...]` dependency ordering |
| mutating hook arguments | `MutableAffair` fields |

### What changes in practice

#### 1. Turn hook specs into affair classes

In pluggy, the contract is a function signature. In affairon, the contract is a
typed model.

```python
# pluggy
@hookspec
def add_ingredients(ingredients): ...

# affairon
from affairon import Affair

class AddIngredients(Affair):
    ingredients: tuple[str, ...]
```

Use `Affair` for immutable input. Use `MutableAffair` when listeners are meant
to update fields in place.

#### 2. Turn hook implementations into listeners

Replace `@hookimpl` with `@listen(...)` or `@dispatcher.on(...)`. A listener
returns `dict | None`; the dispatcher merges all returned dictionaries.

```python
from affairon import listen

@listen(AddIngredients)
def add_spam(affair: AddIngredients) -> dict[str, list[str]]:
    return {"ingredients_spam": ["lovely spam", "wonderous spam"]}
```

For class-based plugins, `AffairAware` gives you a class container for bound
listeners.

#### 3. Replace hook calls with `emit()`

Pluggy usually gives the host a list of results. Affairon gives the host a
merged dictionary, so the host becomes explicit about how to combine listener
contributions.

```python
result = dispatcher.emit(AddIngredients(ingredients=("egg",)))
items = [item for values in result.values() for item in values]
```

This is the main mental shift: listeners collaborate on a seam, and the host
decides how to consume the merged result.

#### 4. Move plugin wiring into `pyproject.toml`

Instead of manually building a `PluginManager`, declare local and external
plugins in `[tool.affairon]` and let `fairun` compose them.

```toml
[tool.affairon]
plugins = ["my-plugin>=1.0"]
local_plugins = ["myapp.lib", "myapp.host"]
```

`fairun` reads `pyproject.toml`, composes the configured plugins onto the chosen
dispatcher, and emits `AffairMain` to start the application.

#### 5. Re-think ordering and conditions

Pluggy's `tryfirst` / `trylast` are priority hints. Affairon uses explicit
dependency ordering with `after=[...]`, plus `when=` predicates for conditional
execution.

If your pluggy setup has simple ordering rules, `after=[...]` is usually enough.
If it has complex wrapper-style control flow, treat the migration as a redesign,
not a search-and-replace.

### Notes for pluggy users

- You usually do not need an `optionalhook` equivalent. In affairon, a listener
  simply does not register for a seam it does not implement.
- `MutableAffair` is the place for shared mutable state. Standard `Affair`
  instances stay immutable.
- `when=` and `emit_up=True` are worth using during migration. They often let
  you replace pluggy-side conditional logic with cleaner dispatcher behavior.
- `AsyncDispatcher` is the async path. Same-layer listeners run concurrently
  once their ordering constraints are satisfied.
- Some pluggy features do not have a documented 1:1 affairon counterpart today,
  especially wrapper-style hooks, historic calls, and first-result semantics.
  When you depend on those, migrate the behavior intentionally instead of trying
  to mirror pluggy's API shape.

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
