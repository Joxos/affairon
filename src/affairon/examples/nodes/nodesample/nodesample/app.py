from __future__ import annotations

from affairon import Dispatcher

from nodesample.nodes import Clock, Room


def build_room() -> tuple[Room, Dispatcher]:
    dispatcher = Dispatcher()
    room = Room()
    room.provide(Clock())
    room.attach_dispatcher(dispatcher)
    return room, dispatcher


def demo() -> dict[str, object]:
    room, _dispatcher = build_room()
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
