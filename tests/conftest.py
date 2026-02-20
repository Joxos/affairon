"""Shared affair types for affairon tests."""

from affairon import Affair, MutableAffair


class Ping(Affair):
    msg: str


class Pong(Affair):
    msg: str


class MutablePing(MutableAffair):
    msg: str


# Hierarchy for emit_up tests (ParentAffair -> ChildAffair -> GrandchildAffair)


class ParentAffair(MutableAffair):
    msg: str


class ChildAffair(ParentAffair):
    extra: str


class GrandchildAffair(ChildAffair):
    detail: str
