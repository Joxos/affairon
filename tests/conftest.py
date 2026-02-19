"""Shared affair types for affairon tests."""

from affairon import Affair, MutableAffair


class Ping(Affair):
    msg: str


class Pong(Affair):
    msg: str


class MutablePing(MutableAffair):
    msg: str
