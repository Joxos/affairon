from __future__ import annotations

from typing import cast

from affairon import AffairMain, Dispatcher, default_dispatcher, listen
from duelsample.nodes import Duel, Player, PlayerLifePoint, PlayerRuntime


@listen(AffairMain)
def run(_affair: AffairMain) -> dict[str, object]:
    dispatcher = Dispatcher()
    duel = Duel().attach_dispatcher(dispatcher)
    player = cast(Player, duel.mount(Player()))
    player.provide(PlayerRuntime("Yugi"))

    lp = cast(PlayerLifePoint, player.lp)
    lp.set_points(8000)
    lp.lose(500)
    lp.gain(200)

    return {
        "phase": "demo",
        "life_points": lp.life_points,
        "dispatcher": default_dispatcher is not None,
    }
