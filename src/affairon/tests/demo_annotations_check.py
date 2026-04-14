from __future__ import annotations

from tests.demo_annotations import (
    Clock,
    MemberList,
    MemberStats,
    MessageLog,
    build_room,
)

room, _dispatcher = build_room()


def takes_log(x: MessageLog) -> None: ...
def takes_members(x: MemberList) -> None: ...
def takes_stats(x: MemberStats) -> None: ...
def takes_dict_str_bool(x: dict[str, bool]) -> None: ...
def takes_dict_str_int(x: dict[str, int]) -> None: ...
def takes_clock(x: Clock) -> None: ...


takes_log(room.log)
takes_members(room.members)
takes_stats(room.members.stats)
takes_dict_str_bool(room.members.join("Alice"))
takes_dict_str_int(room.log.record("Alice", "hi"))
takes_dict_str_int(room.members.stats.bump("Alice"))
takes_clock(room.inject(Clock))

_ = room.members.join(123)
_ = room.log.record("Alice", "hi", "should_fail")
