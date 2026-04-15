from __future__ import annotations

from affairon import Dispatcher
from nodesample.nodes import Room


def build_room() -> tuple[Room, Dispatcher]: ...

def demo() -> dict[str, object]: ...
