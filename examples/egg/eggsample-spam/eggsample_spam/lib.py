from eggsample.affairs import AddIngredients, PrepCondiments
from eggsample.lib import base_condiments

from affairon import default_dispatcher as dispatcher


@dispatcher.on(AddIngredients)
def spam_plugin(affair: AddIngredients) -> dict[str, list[str]]:
    """Here the caller expects us to return a list."""
    if "egg" in affair.ingredients:
        spam = ["lovely spam", "wonderous spam"]
    else:
        spam = ["splendiferous spam", "magnificent spam"]
    return {"ingredients_spam": spam}


@dispatcher.on(
    PrepCondiments, after=[base_condiments]
)  # Pluggy uses LIFO. Here we explicitly specify the order.
def spam_sauce(affair: PrepCondiments) -> dict[str, str]:
    """Here the caller passes a mutable object, so we mess with it directly."""
    try:
        del affair.condiments["steak sauce"]
    except KeyError:
        pass
    affair.condiments["spam sauce"] = 42
    return {"comments_spam": "Now this is what I call a condiments tray!"}
