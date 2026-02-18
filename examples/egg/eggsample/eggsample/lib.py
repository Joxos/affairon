from affairon import default_dispatcher as dispatcher
from eggsample.affairs import AddIngredients, PrepCondiments


@dispatcher.on(AddIngredients)
def base_kitchen(affair: AddIngredients) -> dict[str, list[str]]:
    spices = ["salt", "pepper"]
    you_can_never_have_enough_eggs = ["egg", "egg"]
    return {"ingredients_base": spices + you_can_never_have_enough_eggs}


@dispatcher.on(PrepCondiments)
def base_condiments(affair: PrepCondiments) -> None:
    affair.condiments["mint sauce"] = 1
