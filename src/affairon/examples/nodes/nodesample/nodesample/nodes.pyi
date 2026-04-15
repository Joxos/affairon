from __future__ import annotations

from affairon import Node


class Clock:
    tick: int
    def advance(self) -> int: ...

class MemberList(Node):
    names: list[str]
    stats: MemberStats
    def join(self, name: str) -> None: ...
    def kick(self, name: str) -> None: ...

class MemberStats(Node):
    counts: dict[str, int]
    def bump(self, name: str) -> None: ...

class MessageLog(Node):
    entries: list[dict[str, str | int]]
    def record(self, sender: str, text: str) -> None: ...

class Room(Node):
    log: MessageLog
    members: MemberList
