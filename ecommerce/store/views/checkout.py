from django.conf import settings
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views import View

from store.models.customers import Customer
from store.models.orders import Order
from store.payments import (
    MINIMUM_TOTAL_UNITS,
    build_cart_items,
    build_line_items,
    cart_total,
    get_stripe,
)

# Postal-address fields shared by the checkout form, Customer and Order.
ADDRESS_FIELDS = [
    'recipient_name', 'street_address', 'address_line2',
    'city', 'state', 'zip_code', 'country',
]


def _create_orders(customer, cart_items, address, phone, payment_status,
                   stripe_session_id=''):
    """Persist one Order row per cart line, in a single transaction."""
    with transaction.atomic():
        for item in cart_items:
            Order(
                customer=customer,
                product=item['product'],
                # Snapshot the price so later catalogue edits don't rewrite history.
                price=item['unit_price'],
                quantity=item['qty'],
                phone=phone,
                payment_status=payment_status,
                stripe_session_id=stripe_session_id,
                **address,
            ).save()


class CheckOut(View):
    def get(self, request):
        cart_items = build_cart_items(request.session.get('cart', {}))
        if not cart_items:
            return redirect('cart')

        customer = None
        customer_id = request.session.get('customer')
        if customer_id:
            customer = Customer.objects.filter(id=customer_id).first()

        return render(request, 'checkout.html', {
            'cart_items': cart_items,
            'total': cart_total(cart_items),
            'customer': customer,
            'stripe_enabled': settings.STRIPE_ENABLED,
        })

    def post(self, request):
        customer_id = request.session.get('customer')
        customer = Customer.objects.filter(id=customer_id).first()
        if customer is None:
            return redirect('login')

        address = {f: (request.POST.get(f) or '').strip() for f in ADDRESS_FIELDS}
        phone = (request.POST.get('phone') or '').strip()

        # Optionally remember this address on the customer's profile.
        if request.POST.get('save_address'):
            for field, value in address.items():
                setattr(customer, field, value)
            if phone:
                customer.phone = phone
            customer.save()

        cart_items = build_cart_items(request.session.get('cart', {}))
        if not cart_items:
            return redirect('cart')

        stripe = get_stripe()

        # No Stripe configured: record the order as awaiting payment so the
        # store still works for demos and manual/offline fulfillment.
        if stripe is None:
            _create_orders(customer, cart_items, address, phone,
                           payment_status=Order.PAYMENT_PENDING)
            request.session['cart'] = {}
            return redirect('orders')

        total = cart_total(cart_items)
        if total < MINIMUM_TOTAL_UNITS:
            return self._error(request, cart_items, customer,
                               'El total del pedido es demasiado bajo para procesar el pago.')

        success_url = request.build_absolute_uri(reverse('checkout_success'))
        cancel_url = request.build_absolute_uri(reverse('checkout_cancel'))

        try:
            session = stripe.checkout.Session.create(
                mode='payment',
                line_items=build_line_items(cart_items),
                # Stripe substitutes the real id into this placeholder.
                success_url=f'{success_url}?session_id={{CHECKOUT_SESSION_ID}}',
                cancel_url=cancel_url,
                customer_email=customer.email or None,
                client_reference_id=str(customer.id),
                metadata={'customer_id': str(customer.id)},
            )
        except Exception as exc:  # network error, bad key, invalid amount…
            return self._error(
                request, cart_items, customer,
                f'No pudimos iniciar el pago. Intenta de nuevo. ({exc})')

        # Only recorded once Stripe has accepted the session, so a failure above
        # never leaves phantom orders behind.
        _create_orders(customer, cart_items, address, phone,
                       payment_status=Order.PAYMENT_PENDING,
                       stripe_session_id=session.id)

        # Cart is deliberately kept until payment succeeds — a shopper who
        # cancels on Stripe comes back to a full cart.
        return redirect(session.url)

    def _error(self, request, cart_items, customer, message):
        return render(request, 'checkout.html', {
            'cart_items': cart_items,
            'total': cart_total(cart_items),
            'customer': customer,
            'stripe_enabled': settings.STRIPE_ENABLED,
            'error': message,
        }, status=400)
