"""Affairon reimplementation of pluggy's eggsample.

This mirrors the pluggy docs example where a host defines hook specs for
adding ingredients and preparing condiments, and a spam plugin extends the
meal. Here, affairs are the typed extension seams:

- AddIngredients: gather more ingredients (returns parts to append)
- PrepCondiments: reorganize the condiments tray (returns ops + comments)

Listeners return dicts with *distinct keys* so merges don't conflict. The
host aggregates the merged dict into final outputs.
"""

import itertools
import random
from pathlib import Path

from affairon import Dispatcher
from affairon import default_dispatcher as dispatcher
from affairon.composer import ModuleLoader
from examples.eggsample.affairs import AddIngredients, PrepCondiments

module_loader = ModuleLoader()
module_loader.discover_modules(Path(__file__).parent.parent)


condiments_tray = {
    "pickled walnuts": 13,
    "steak sauce": 4,
    "mushy peas": 2,
}


def main() -> None:
    # All callbacks are registered via the dispatcher decorator, so we don't need a get_plugin_manager() here!
    cook = EggsellentCook(dispatcher)
    cook.add_ingredients()
    cook.prepare_the_food()
    cook.serve_the_food()


class EggsellentCook:
    FAVORITE_INGREDIENTS = (
        str("egg"),  # noqa
        str("egg"),  # noqa
        str("egg"),  # noqa
    )  # to avoid mutation issues when casting to list

    def __init__(self, dispatcher: Dispatcher):
        self.dispatcher = dispatcher
        self.ingredients: list[str] = []

    def add_ingredients(self) -> None:
        result = self.dispatcher.emit(
            AddIngredients(ingredients=self.FAVORITE_INGREDIENTS)
        )
        my_ingredients = list(self.FAVORITE_INGREDIENTS)
        other_ingredients = list(itertools.chain.from_iterable(result.values()))
        self.ingredients = my_ingredients + other_ingredients

    def prepare_the_food(self) -> None:
        random.shuffle(self.ingredients)

    def serve_the_food(self) -> None:
        # In pluggy it pass the reference to the hookimpl and allows in-place mutation.
        # However, affairon uses pydantic models which doesn't support references after v2.
        # So it is necessary to change condiments_tray globally here.
        global condiments_tray
        affair = PrepCondiments(condiments=condiments_tray)
        condiment_comments = self.dispatcher.emit(affair).values()
        condiments_tray = affair.condiments
        print(f"Your food. Enjoy some {', '.join(self.ingredients)}")
        print(f"Some condiments? We have {', '.join(condiments_tray.keys())}")
        if condiment_comments:
            print("\n".join(condiment_comments))


if __name__ == "__main__":
    main()
