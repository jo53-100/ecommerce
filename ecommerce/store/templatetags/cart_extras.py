from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Look up a value in a dict by a key that may be an int or str.

    The cart is stored in the session as {product_id_str: quantity}.
    """
    if not dictionary:
        return 0
    return dictionary.get(str(key), 0)


@register.filter
def mul(value, arg):
    """Multiply value by arg (used for line subtotals)."""
    try:
        return int(value) * int(arg)
    except (ValueError, TypeError):
        return 0
