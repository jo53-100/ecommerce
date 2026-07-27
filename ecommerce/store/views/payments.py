"""Views that close the loop on a Stripe Checkout payment.

Two independent paths can confirm a payment:

* the shopper landing back on `checkout_success` after paying, and
* the `checkout.session.completed` webhook Stripe sends server-to-server.

The webhook is the source of truth (it arrives even if the shopper closes the
tab), but the success page also confirms so the order list is correct the
instant the shopper looks at it. `mark_orders_paid` is idempotent, so whichever
lands second is a no-op.
"""

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from store.models.orders import Order
from store.payments import (
    as_dict,
    get_stripe,
    mark_orders_failed,
    mark_orders_paid,
    mark_orders_refunded,
)


def checkout_success(request):
    """Landing page after a successful Stripe payment."""
    session_id = request.GET.get('session_id', '')
    if not session_id:
        return redirect('orders')

    stripe = get_stripe()
    paid = False

    if stripe is not None:
        try:
            session = as_dict(stripe.checkout.Session.retrieve(session_id))
        except Exception:
            session = {}

        if session.get('payment_status') == 'paid':
            paid = True
            mark_orders_paid(session_id, session.get('payment_intent') or '')

    if paid:
        # Only now is it safe to empty the cart.
        request.session['cart'] = {}

    orders = (Order.objects
              .filter(stripe_session_id=session_id)
              .order_by('id'))

    return render(request, 'checkout_success.html', {
        'orders': orders,
        'paid': paid,
        'total': sum(o.line_total for o in orders),
    })


def checkout_cancel(request):
    """Shopper backed out on Stripe — cart is untouched, so send them to it."""
    return render(request, 'checkout_cancel.html')


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Receive payment events from Stripe.

    CSRF-exempt because Stripe cannot present a Django CSRF token; the request
    is authenticated instead by verifying the signature header against the
    endpoint's signing secret.
    """
    stripe = get_stripe()
    if stripe is None or not settings.STRIPE_WEBHOOK_SECRET:
        # Refuse rather than trusting unverifiable payloads.
        return HttpResponseBadRequest('Stripe webhooks are not configured.')

    payload = request.body
    signature = request.META.get('HTTP_STRIPE_SIGNATURE', '')

    try:
        event = stripe.Webhook.construct_event(
            payload, signature, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError:
        return HttpResponseBadRequest('Invalid payload.')
    except stripe.SignatureVerificationError:
        return HttpResponseBadRequest('Invalid signature.')

    event_type = event['type']
    obj = as_dict(event['data']['object'])

    if event_type == 'checkout.session.completed':
        # `completed` can still be unpaid for async methods, so check.
        if obj.get('payment_status') == 'paid':
            mark_orders_paid(obj['id'], obj.get('payment_intent') or '')
    elif event_type == 'checkout.session.async_payment_succeeded':
        mark_orders_paid(obj['id'], obj.get('payment_intent') or '')
    elif event_type in ('checkout.session.expired',
                        'checkout.session.async_payment_failed'):
        mark_orders_failed(obj['id'])
    elif event_type == 'charge.refunded':
        # A Charge, not a Session — it carries the payment intent, which is the
        # only handle back to the orders. Refunding returns the stock.
        mark_orders_refunded(obj.get('payment_intent') or '')

    # Any 2xx tells Stripe the event was received; unknown types are ignored.
    return HttpResponse(status=200)
