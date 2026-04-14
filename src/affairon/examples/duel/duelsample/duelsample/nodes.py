from __future__ import annotations

from typing import Annotated

from affairon import Affair, Node, Parent, associate, root, route


class PlayerRuntime:
    def __init__(self, name: str) -> None:
        self.name = name


@route("life")
class LifePoint(Node):
    SetLifePointsAffair: Affair
    LoseLifePointsAffair: Affair

    def __init__(self) -> None:
        super().__init__()
        self.life_points = 0

    @associate(LoseLifePointsAffair)
    def lose(self, amount: int) -> dict[str, int]:
        self.life_points -= amount
        return {"life_points": self.life_points}

    @associate(SetLifePointsAffair)
    def set_points(self, amount: int) -> dict[str, int]:
        self.life_points = amount
        return {"life_points": self.life_points}

    @associate(type("GainLifePointsAffair", (), {}))
    def gain(self, amount: int) -> dict[str, int]:
        self.life_points += amount
        return {"life_points": self.life_points}


@route("player")
class Player(Node):
    pass


@LifePoint.inject
@route("lp")
class LifeLog(Node):
    DescribeLifeAffair: Affair

    @associate(DescribeLifeAffair)
    def describe(
        self,
        runtime: Annotated[PlayerRuntime, Parent / Player / PlayerRuntime],
    ) -> dict[str, str]:
        return {"player": runtime.name}


@Player.inject
@route("lp")
class PlayerLifePoint(LifePoint):
    pass


@root
@route("duel")
class Duel(Node):
    pass
