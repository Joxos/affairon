# Node system example -- chat room

This example builds a chat room as an affairon node tree, exercising every
Node feature in one coherent app.

## Tree structure

```
Room (@root)
+-- log: MessageLog
|     record(sender, text) -> RecordAffair
+-- members: MemberList
      join(name) -> JoinAffair
      kick(name) -> KickAffair
      +-- stats: MemberStats  (auto-mounted via inject_to)
            bump(name) -> BumpAffair
```

## What it demonstrates

**@root / @route** -- `Room` is marked `@root`, so it auto-mounts all
`inject_to(Room)` classes when instantiated.  `@route("log")` on `MessageLog`
means it ends up as `room.log`.

**inject_to()** -- `MemberStats` uses `@inject_to(MemberList)` to attach itself
under `MemberList` automatically.  No manual `mount()` call needed.  This
replaced the earlier `@Parent.inject` decorator, which was removed because
`inject` on a class (returning a decorator) clashed with `inject` on an
instance (looking up a runtime object).

**affair() + @associate** -- each node declares affair slots with `affair()`
and binds handlers with `@associate`.  The framework generates a
`MutableAffair` subclass from the handler's parameter signature.  After
`attach_dispatcher()`, emitting that affair triggers the handler.  The handler
can also be called directly as a plain method.

**provide() / inject()** -- `Room` stores a `Clock` object in its per-node
runtime registry via `room.provide(Clock())`.  This is how helper objects
(configs, caches, timers) are shared within a node's scope.  It's a simple
type-keyed store: `provide(obj)` stores by `type(obj)`, `inject(Type)`
retrieves it.

**Locator paths** -- `MessageLog.record` needs the `Clock` from the root
node, so its parameter is annotated `Annotated[Clock, Root / Clock]`.  The
framework calls `root.inject(Clock)` automatically.  `MemberStats.bump` uses
`Annotated[MemberList, Parent / MemberList]` to get a reference to its parent
node.

**attach_dispatcher()** -- `build_room()` creates a `Dispatcher`, builds the
tree, then calls `room.attach_dispatcher(dispatcher)` to wire every
`@associate` handler as a dispatcher listener.

**Direct method calls** -- `room.members.join("Alice")` calls the handler
directly.  Injection still works.  You don't have to go through
`dispatcher.emit()` for everything.

## Run

```bash
cd nodesample
uv sync
uv run fairun .
```

Expected output:

```
Members: ['Alice', 'Bob']
Messages logged: 3
Alice sent: 2, Bob sent: 1
Clock ticks: 3
```
