from affairon import Affair, MutableAffair


class AddIngredients(Affair):
    """Have a look at the ingredients and offer your own.

    :return: a list of ingredients
    """

    # The ingredients, don't touch them!
    ingredients: tuple[str, ...]


class PrepCondiments(MutableAffair):
    """Reorganize the condiments tray to your heart's content.

    :return: a witty comment about your activity
    """

    # some sauces and stuff
    condiments: dict[str, int]
