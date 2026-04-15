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

from affairon import MutableAffair, Node, Parent, Root, affair, associate, inject_to, root, route


class Clock:
    """Plain helper object, stored in the root's registry via provide().

    This is not a node -- it's just an ordinary object.  Nodes that need
    a clock get it through inject() (same-node) or a locator path
    (cross-node, e.g. ``Annotated[Clock, Root / Clock]``).
    """

    def __init__(self) -> None:
        self.tick: int = 0

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

    RecordAffair: type[MutableAffair] = affair()

    @associate(RecordAffair)
    def record(
        self,
        sender: str,
        text: str,
        clock: Annotated[Clock, Root / Clock],
    ) -> None:
        """Record a message.  The clock parameter is injected automatically.

        ``Root / Clock`` means: starting from the tree root, call
        inject(Clock).  The root's registry has a Clock because
        build_room() calls room.provide(Clock()).
        """
        ts = clock.advance()
        self.entries.append({"sender": sender, "text": text, "ts": ts})


@inject_to(Room)
@route("members")
class MemberList(Node):
    def __init__(self) -> None:
        super().__init__()
        self.names: list[str] = []

    JoinAffair = affair()
    KickAffair = affair()

    @associate(JoinAffair)
    def join(self, name: str) -> None:
        self.names.append(name)

    @associate(KickAffair)
    def kick(self, name: str) -> None:
        self.names.remove(name)


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
    ) -> None:
        """Bump message count for a member.

        ``Parent / MemberList`` means: go to this node's parent, and since
        the parent is a MemberList, resolve it directly.  This gives the
        handler read access to the parent's member list without storing
        a reference manually.
        """
        if name not in members.names:
            raise ValueError(f"{name} is not a member")
        self.counts[name] = self.counts.get(name, 0) + 1
