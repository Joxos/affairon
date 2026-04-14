"""Node system example -- a chat room built on affairon's node tree.

Tree layout::

    Room (@root)
    +-- log: MessageLog
    |     record() -> RecordAffair
    +-- members: MemberList
          join() -> JoinAffair
          kick() -> KickAffair
          +-- stats: MemberStats  (auto-mounted via inject_to)
                bump() -> BumpAffair

Features demonstrated:

- @root / @route -- declaring the tree structure
- inject_to() -- auto-mounting children without manual mount() calls
- affair() + @associate -- declaring affairs and binding handlers
- provide() / inject() -- per-node runtime registry for helper objects
- Locator paths (Root / ..., Parent / ...) -- cross-node dependency injection
- attach_dispatcher() -- wiring the tree to an event bus
- Direct method calls -- handlers work as plain methods too
"""

from __future__ import annotations

from typing import Annotated

from affairon import (
    Dispatcher,
    Node,
    Parent,
    Root,
    affair,
    associate,
    inject_to,
    root,
    route,
)


class Clock:
    """Plain helper object, stored in the root's registry via provide().

    This is not a node -- it's just an ordinary object.  Nodes that need
    a clock get it through inject() (same-node) or a locator path
    (cross-node, e.g. ``Annotated[Clock, Root / Clock]``).
    """

    def __init__(self) -> None:
        self.tick = 0

    def advance(self) -> int:
        self.tick += 1
        return self.tick


# -- Root node ---------------------------------------------------------------
# @root means Room auto-mounts any inject_to(Room) classes at construction time.
# @route("room") names the node for potential parent mounting (not used here
# since Room is the root, but it's good practice).


@root
@route("room")
class Room(Node):
    pass


# -- First-level children of Room -------------------------------------------
# inject_to(Room) registers MessageLog and MemberList as auto-mounted children.
# When Room() is created, it instantiates MessageLog() and MemberList() and
# mounts them as room.log and room.members respectively.


@inject_to(Room)
@route("log")
class MessageLog(Node):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[dict[str, str | int]] = []

    RecordAffair = affair()

    @associate(RecordAffair)
    def record(
        self,
        sender: str,
        text: str,
        clock: Annotated[Clock, Root / Clock],
    ) -> dict[str, int]:
        """Record a message.  The clock parameter is injected automatically.

        ``Root / Clock`` means: starting from the tree root, call
        inject(Clock).  The root's registry has a Clock because
        build_room() calls room.provide(Clock()).
        """
        ts = clock.advance()
        self.entries.append({"sender": sender, "text": text, "ts": ts})
        return {"ts": ts}


@inject_to(Room)
@route("members")
class MemberList(Node):
    def __init__(self) -> None:
        super().__init__()
        self.names: list[str] = []

    JoinAffair = affair()
    KickAffair = affair()

    @associate(JoinAffair)
    def join(self, name: str) -> dict[str, bool]:
        if name in self.names:
            return {"joined": False}
        self.names.append(name)
        return {"joined": True}

    @associate(KickAffair)
    def kick(self, name: str) -> dict[str, bool]:
        if name not in self.names:
            return {"kicked": False}
        self.names.remove(name)
        return {"kicked": True}


# -- Second-level child (grandchild of Room) ---------------------------------
# inject_to(MemberList) means MemberStats is auto-mounted under MemberList,
# accessible as room.members.stats.


@inject_to(MemberList)
@route("stats")
class MemberStats(Node):
    def __init__(self) -> None:
        super().__init__()
        self.counts: dict[str, int] = {}

    BumpAffair = affair()

    @associate(BumpAffair)
    def bump(
        self,
        name: str,
        members: Annotated[MemberList, Parent / MemberList],
    ) -> dict[str, int]:
        """Bump message count for a member.

        ``Parent / MemberList`` means: go to this node's parent, and since
        the parent is a MemberList, resolve it directly.  This gives the
        handler read access to the parent's member list without storing
        a reference manually.
        """
        if name not in members.names:
            raise ValueError(f"{name} is not a member")
        self.counts[name] = self.counts.get(name, 0) + 1
        return {"count": self.counts[name]}


def build_room() -> tuple[Room, Dispatcher]:
    """Build and wire a complete chat room.

    1. Create the room -- @root auto-mounts MessageLog, MemberList, and
       MemberStats (as a grandchild via inject_to chain).
    2. Provide a Clock to the root's runtime registry.
    3. Attach a dispatcher so @associate handlers are registered as listeners.
    """
    dispatcher = Dispatcher()
    room = Room()
    room.provide(Clock())
    room.attach_dispatcher(dispatcher)
    return room, dispatcher


def demo() -> dict[str, object]:
    room, _dispatcher = build_room()

    # Direct method calls -- no dispatcher.emit() needed.
    # The methods work as plain calls; injection still happens.
    room.members.join("Alice")
    room.members.join("Bob")

    room.log.record("Alice", "hello everyone")
    room.members.stats.bump("Alice")

    room.log.record("Bob", "hey Alice!")
    room.members.stats.bump("Bob")

    room.log.record("Alice", "let's kick Eve")
    room.members.stats.bump("Alice")

    room.members.join("Eve")
    room.members.kick("Eve")

    return {
        "members": list(room.members.names),
        "log_count": len(room.log.entries),
        "alice_msgs": room.members.stats.counts.get("Alice", 0),
        "bob_msgs": room.members.stats.counts.get("Bob", 0),
        "clock": room.inject(Clock).tick,
    }
