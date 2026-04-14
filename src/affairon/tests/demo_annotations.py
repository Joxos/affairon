"""Demo: explicit annotations on parent nodes for static type visibility.

The developer declares child node types as class annotations on the parent.
inject_to() handles the runtime wiring. The type checker sees the annotations
directly from the source code — no stub needed.
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
    def __init__(self) -> None:
        self.tick = 0

    def advance(self) -> int:
        self.tick += 1
        return self.tick


@root
@route("room")
class Room(Node):
    log: MessageLog
    members: MemberList


@inject_to(Room)
@route("log")
class MessageLog(Node):
    def __init__(self) -> None:
        super().__init__()
        self.entries: list[str] = []

    RecordAffair = affair()

    @associate(RecordAffair)
    def record(
        self,
        sender: str,
        text: str,
        clock: Annotated[Clock, Root / Clock],
    ) -> dict[str, int]:
        ts = clock.advance()
        self.entries.append(f"{sender}: {text} @{ts}")
        return {"ts": ts}


@inject_to(Room)
@route("members")
class MemberList(Node):
    def __init__(self) -> None:
        super().__init__()
        self.names: list[str] = []

    stats: MemberStats

    JoinAffair = affair()

    @associate(JoinAffair)
    def join(self, name: str) -> dict[str, bool]:
        if name in self.names:
            return {"joined": False}
        self.names.append(name)
        return {"joined": True}


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
        if name not in members.names:
            raise ValueError(f"{name} is not a member")
        self.counts[name] = self.counts.get(name, 0) + 1
        return {"count": self.counts[name]}


def build_room() -> tuple[Room, Dispatcher]:
    dispatcher = Dispatcher()
    room = Room()
    room.provide(Clock())
    room.attach_dispatcher(dispatcher)
    return room, dispatcher
