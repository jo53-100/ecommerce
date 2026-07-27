"""Stripe Checkout helpers.

The money-handling rules this module exists to enforce:

1. Prices are ALWAYS read from the database, never from the request. A client
   that POSTs `price=1` must not be able to buy a $400 item for a dollar.
2. Amounts are sent to Stripe in the currency's smallest unit (centavos), which
   is what `to_stripe_amount` is for. Everywhere else money is a Decimal.
3. Marking an order paid is idempotent — Stripe retries webhooks, and the
   success page may also confirm a payment the webhook already recorded.
4. Stock moves only when money moves. Inventory is decremented in the same
   transaction that flips an order to paid, and put back when it is refunded.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from store.models.orders import Order
from store.models.products import Products

# Stripe rejects charges below roughly $0.50 in most currencies.
MINIMUM_TOTAL_UNITS = Decimal('1.00')

CENTS = Decimal('0.01')


def get_stripe():
    """Return a configured stripe module, or None when Stripe is unavailable.

    Importing lazily keeps the rest of the store working if the library is not
    installed yet — only the payment path degrades, not the whole site.
    """
    if not settings.STRIPE_ENABLED:
        return None
    try:
        import stripe
    except ImportError:
        return None
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def as_dict(stripe_object):
    """Normalise a Stripe SDK object into a plain dict.

    `StripeObject` is not a dict subclass — it supports `obj['key']` but NOT
    `obj.get('key')`, which raises AttributeError. Converting up front means
    callers can use ordinary `.get()` with defaults for optional fields.
    """
    if stripe_object is None:
        return {}
    to_dict = getattr(stripe_object, 'to_dict', None)
    if callable(to_dict):
        return to_dict()
    return dict(stripe_object)


def parse_cart_key(key):
    """Split a session cart key into (product_id, color).

    Keys look like "12" or "12_navy" — the colour suffix is optional.
    """
    parts = str(key).split('_')
    return parts[0], (parts[1] if len(parts) > 1 else None)


def to_stripe_amount(price_in_units):
    """Convert a price in major units to Stripe's minor units.

    400 -> 40000, Decimal('99.99') -> 9999. Stripe only accepts integers, so
    the value is quantised to two places with banker's-rounding disabled
    (ROUND_HALF_UP) — a half-centavo always rounds in the same, predictable
    direction rather than to even.
    """
    amount = Decimal(price_in_units).quantize(CENTS, rounding=ROUND_HALF_UP)
    return int(amount * 100)


def build_cart_items(cart):
    """Resolve a session cart dict into concrete, priced line items.

    Returns a list of dicts with the product pulled fresh from the database.
    Unknown product ids and non-positive quantities are dropped rather than
    raising, so a stale cookie can never break checkout.
    """
    if not cart:
        return []

    product_ids = [parse_cart_key(k)[0] for k in cart.keys()]
    products = {str(p.id): p for p in Products.get_products_by_id(product_ids)}

    items = []
    for key, qty in cart.items():
        product_id, color = parse_cart_key(key)
        product = products.get(product_id)
        if product is None:
            continue
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            continue
        if qty < 1:
            continue
        items.append({
            'cart_key': key,
            'product': product,
            'color': color,
            'qty': qty,
            # Priced from the DB row, never from the request.
            'unit_price': product.price,
            'subtotal': product.price * qty,
            # Surfaced so the cart and checkout pages can flag a problem line
            # before the shopper is sent to Stripe.
            'available': product.can_supply(qty),
        })
    return items


def cart_total(cart_items):
    # Seeded with a Decimal so an empty cart totals 0.00, not the int 0.
    return sum((item['subtotal'] for item in cart_items), Decimal('0.00'))


def out_of_stock_items(cart_items):
    """Return the cart lines that cannot currently be fulfilled."""
    return [item for item in cart_items if not item['available']]


def build_line_items(cart_items):
    """Translate resolved cart items into Stripe `line_items` payload."""
    line_items = []
    for item in cart_items:
        name = item['product'].name
        if item['color']:
            name = f"{name} ({item['color']})"
        line_items.append({
            'price_data': {
                'currency': settings.STRIPE_CURRENCY,
                'unit_amount': to_stripe_amount(item['unit_price']),
                'product_data': {'name': name},
            },
            'quantity': item['qty'],
        })
    return line_items


def _apply_stock_delta(orders, sign):
    """Move stock by `sign` units per order line (-1 to consume, +1 to return).

    F() expressions push the arithmetic into the database, so two concurrent
    payments for the last item cannot both read the same starting figure and
    write the same decremented one.
    """
    for order in orders:
        (Products.objects
         .filter(pk=order.product_id, track_inventory=True)
         .update(stock=F('stock') + sign * order.quantity))


def mark_orders_paid(session_id, payment_intent=''):
    """Flip every order from one checkout session to paid and consume stock.

    Idempotent, and that matters twice over here: Stripe retries webhooks and
    the success page may confirm a payment the webhook already recorded, so
    without care the same sale could be deducted from inventory twice. The
    rows are locked and filtered on not-yet-paid inside one transaction, so
    exactly one caller sees the transition and only that caller moves stock.

    Returns the number of rows actually updated.
    """
    if not session_id:
        return 0

    with transaction.atomic():
        orders = list(
            Order.objects
            .select_for_update()
            .filter(stripe_session_id=session_id)
            .exclude(payment_status=Order.PAYMENT_PAID)
        )
        if not orders:
            return 0

        updated = (
            Order.objects
            .filter(pk__in=[o.pk for o in orders])
            .update(
                payment_status=Order.PAYMENT_PAID,
                stripe_payment_intent=payment_intent or '',
                paid_at=timezone.now(),
            )
        )
        _apply_stock_delta(orders, sign=-1)

    return updated


def mark_orders_refunded(payment_intent):
    """Mark a payment's orders refunded and put the stock back on the shelf.

    Keyed on the payment intent rather than the session id because that is
    what Stripe's `charge.refunded` event carries. Same locking rationale as
    `mark_orders_paid`: only the caller that observes the paid -> refunded
    transition restocks, so a retried webhook cannot inflate inventory.
    """
    if not payment_intent:
        return 0

    with transaction.atomic():
        orders = list(
            Order.objects
            .select_for_update()
            .filter(stripe_payment_intent=payment_intent,
                    payment_status=Order.PAYMENT_PAID)
        )
        if not orders:
            return 0

        updated = (
            Order.objects
            .filter(pk__in=[o.pk for o in orders])
            .update(payment_status=Order.PAYMENT_REFUNDED)
        )
        _apply_stock_delta(orders, sign=+1)

    return updated


def mark_orders_failed(session_id):
    """Mark a checkout's orders as failed (expired or declined session)."""
    if not session_id:
        return 0
    return (
        Order.objects
        .filter(stripe_session_id=session_id,
                payment_status=Order.PAYMENT_PENDING)
        .update(payment_status=Order.PAYMENT_FAILED)
    )
