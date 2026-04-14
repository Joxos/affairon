"""Locator path expressions for cross-node resolution.

Locators let ``@associate`` handlers declare dependencies on objects living
in other nodes.  The ``/`` operator composes path segments into a
:class:`Locator`, which the node tree resolves at call time.

Two anchors are provided:

- ``Root`` -- start from the tree root.
- ``Parent`` -- start from the current node's parent.

Segments can be types (resolved via ``inject()`` or route lookup) or
strings (resolved as attribute names / route names).

Example::

    from typing import Annotated
    from affairon import Root, Parent

    @associate(RecordAffair)
    def record(
        self,
        msg: str,
        clock: Annotated[Clock, Root / Clock],           # root's registry
        parent: Annotated[MemberList, Parent / MemberList],  # parent node
    ) -> dict[str, int]:
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocatorAnchor:
    name: str

    def __truediv__(self, other: Any) -> Locator:
        return Locator((self,)).__truediv__(other)

    def __repr__(self) -> str:
        return self.name


@dataclass(frozen=True)
class Locator:
    segments: tuple[object, ...]

    def __truediv__(self, other: Any) -> Locator:
        if isinstance(other, Locator):
            return Locator(self.segments + other.segments)
        if (
            isinstance(other, LocatorAnchor)
            or isinstance(other, type)
            or isinstance(other, str)
        ):
            return Locator(self.segments + (other,))
        raise TypeError(f"Unsupported locator segment: {other!r}")

    def __repr__(self) -> str:
        return " / ".join(_segment_name(part) for part in self.segments)


def _segment_name(part: object) -> str:
    if isinstance(part, LocatorAnchor):
        return part.name
    if isinstance(part, type):
        return part.__name__
    return repr(part)


Root = LocatorAnchor("Root")
Parent = LocatorAnchor("Parent")

__all__ = ["Locator", "LocatorAnchor", "Parent", "Root"]
