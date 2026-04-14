from __future__ import annotations

import pytest

from affairon import Parent, Root
from affairon.locator import Locator


class AState:
    pass


class BState:
    pass


def test_locator_slash_builds_path() -> None:
    locator = Root / AState / BState

    assert isinstance(locator, Locator)
    assert locator.segments == (Root, AState, BState)


def test_parent_locator_chains() -> None:
    locator = Parent / Parent / AState

    assert locator.segments == (Parent, Parent, AState)


def test_invalid_locator_segment_raises_type_error() -> None:
    with pytest.raises(TypeError, match="Unsupported locator segment"):
        _ = Root / 3
