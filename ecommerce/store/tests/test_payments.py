"""Stripe integration.

No test here touches the network. The Stripe SDK is mocked at the seam
(`get_stripe`), except for webhook signature verification, which runs against
the real `stripe.Webhook.construct_event` using a genuinely computed HMAC — the
part worth testing for real, since it is what keeps forged payment
notifications out.
"""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.urls import reverse
from stripe import StripeObject

from store.models.orders import Order
from store.payments import (
    as_dict,
    build_cart_items,
    build_line_items,
    mark_orders_failed,
    mark_orders_paid,
    to_stripe_amount,
)

from .base import StoreTestCase

WEBHOOK_SECRET = 'whsec_testsecret'
SESSION_ID = 'cs_test_abc123'

ADDRESS = {
    'recipient_name': 'Ana Marina',
    'street_address': 'Calle Naval 123',
    'city': 'Veracruz',
    'state': 'Veracruz',
    'zip_code': '91700',
    'country': 'México',
    'phone': '5551234567',
}


def stripe_signature(payload: bytes, secret: str, timestamp=None) -> str:
    """Build a real Stripe-Signature header for `payload`."""
    timestamp = timestamp or int(time.time())
    signed = f'{timestamp}.'.encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f't={timestamp},v1={digest}'


def fake_stripe_module(session_id=SESSION_ID, url='https://checkout.stripe.com/pay/x'):
    """A stand-in for the stripe module that records calls instead of paying."""
    module = MagicMock()
    created = MagicMock()
    created.id = session_id
    created.url = url
    module.checkout.Session.create.return_value = created
    return module


# ---------------------------------------------------------------------------
# Amount arithmetic — the most expensive thing to get wrong
# ---------------------------------------------------------------------------

class AmountConversionTests(StoreTestCase):

    def test_whole_units_convert_to_cents(self):
        self.assertEqual(to_stripe_amount(400), 40000)
        self.assertEqual(to_stripe_amount(25), 2500)
        self.assertEqual(to_stripe_amount(1), 100)

    def test_line_items_carry_db_prices(self):
        items = build_cart_items({str(self.product.id): 2})
        line_items = build_line_items(items)
        self.assertEqual(len(line_items), 1)
        self.assertEqual(line_items[0]['price_data']['unit_amount'], 40000)
        self.assertEqual(line_items[0]['quantity'], 2)

    def test_line_item_name_includes_colour_variant(self):
        items = build_cart_items({f'{self.product.id}_navy': 1})
        name = build_line_items(items)[0]['price_data']['product_data']['name']
        self.assertIn(self.product.name, name)
        self.assertIn('navy', name)

    @override_settings(STRIPE_CURRENCY='mxn')
    def test_currency_comes_from_settings(self):
        items = build_cart_items({str(self.product.id): 1})
        self.assertEqual(build_line_items(items)[0]['price_data']['currency'], 'mxn')


# ---------------------------------------------------------------------------
# Starting a payment
# ---------------------------------------------------------------------------

@override_settings(STRIPE_ENABLED=True, STRIPE_SECRET_KEY='sk_test_x')
class StartCheckoutTests(StoreTestCase):

    def setUp(self):
        super().setUp()
        self.login()
        self.set_cart({str(self.product.id): 2})

    def test_redirects_the_shopper_to_stripe(self):
        fake = fake_stripe_module()
        with patch('store.views.checkout.get_stripe', return_value=fake):
            response = self.client.post('/check-out/', ADDRESS)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, 'https://checkout.stripe.com/pay/x')

    def test_creates_pending_orders_tagged_with_the_session(self):
        fake = fake_stripe_module()
        with patch('store.views.checkout.get_stripe', return_value=fake):
            self.client.post('/check-out/', ADDRESS)
        order = Order.objects.get()
        self.assertEqual(order.payment_status, Order.PAYMENT_PENDING)
        self.assertEqual(order.stripe_session_id, SESSION_ID)

    def test_cart_survives_until_payment_completes(self):
        """Cancelling on Stripe must not cost the shopper their cart."""
        fake = fake_stripe_module()
        with patch('store.views.checkout.get_stripe', return_value=fake):
            self.client.post('/check-out/', ADDRESS)
        self.assertEqual(self.get_cart(), {str(self.product.id): 2})

    def test_amount_sent_to_stripe_matches_the_catalogue(self):
        fake = fake_stripe_module()
        with patch('store.views.checkout.get_stripe', return_value=fake):
            self.client.post('/check-out/', dict(ADDRESS, price='1'))
        kwargs = fake.checkout.Session.create.call_args.kwargs
        line_item = kwargs['line_items'][0]
        self.assertEqual(line_item['price_data']['unit_amount'], 40000)
        self.assertEqual(line_item['quantity'], 2)

    def test_success_url_carries_the_session_placeholder(self):
        fake = fake_stripe_module()
        with patch('store.views.checkout.get_stripe', return_value=fake):
            self.client.post('/check-out/', ADDRESS)
        kwargs = fake.checkout.Session.create.call_args.kwargs
        self.assertIn('{CHECKOUT_SESSION_ID}', kwargs['success_url'])
        self.assertIn(reverse('checkout_cancel'), kwargs['cancel_url'])

    def test_stripe_failure_creates_no_orders(self):
        fake = fake_stripe_module()
        fake.checkout.Session.create.side_effect = Exception('card_error')
        with patch('store.views.checkout.get_stripe', return_value=fake):
            response = self.client.post('/check-out/', ADDRESS)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)


# ---------------------------------------------------------------------------
# Confirming a payment
# ---------------------------------------------------------------------------

class StripeObjectNormalisationTests(StoreTestCase):
    """`StripeObject` supports obj['k'] but not obj.get('k').

    Reading an optional field straight off a StripeObject raises
    AttributeError, which would 500 the webhook on any event missing an
    optional key. `as_dict` is the guard; these tests keep it honest.
    """

    def test_stripe_object_really_lacks_get(self):
        obj = StripeObject.construct_from({'id': 'cs_1'}, 'sk_test')
        with self.assertRaises(AttributeError):
            obj.get('id')

    def test_as_dict_makes_get_safe(self):
        obj = StripeObject.construct_from(
            {'id': 'cs_1', 'payment_status': 'paid'}, 'sk_test')
        data = as_dict(obj)
        self.assertEqual(data.get('payment_status'), 'paid')
        self.assertIsNone(data.get('payment_intent'))

    def test_as_dict_passes_plain_dicts_through(self):
        self.assertEqual(as_dict({'a': 1}), {'a': 1})

    def test_as_dict_handles_none(self):
        self.assertEqual(as_dict(None), {})


class MarkOrdersPaidTests(StoreTestCase):

    def _order(self, session_id=SESSION_ID):
        return Order.objects.create(
            customer=self.customer, product=self.product,
            price=400, quantity=1, stripe_session_id=session_id,
            payment_status=Order.PAYMENT_PENDING)

    def test_marks_every_order_in_the_session(self):
        self._order()
        self._order()
        self.assertEqual(mark_orders_paid(SESSION_ID, 'pi_1'), 2)
        self.assertTrue(all(o.is_paid for o in Order.objects.all()))

    def test_is_idempotent(self):
        """Stripe retries webhooks — the second delivery must change nothing."""
        self._order()
        self.assertEqual(mark_orders_paid(SESSION_ID, 'pi_1'), 1)
        self.assertEqual(mark_orders_paid(SESSION_ID, 'pi_1'), 0)

    def test_records_the_payment_intent_and_timestamp(self):
        self._order()
        mark_orders_paid(SESSION_ID, 'pi_abc')
        order = Order.objects.get()
        self.assertEqual(order.stripe_payment_intent, 'pi_abc')
        self.assertIsNotNone(order.paid_at)

    def test_leaves_other_sessions_alone(self):
        self._order(session_id='cs_other')
        self.assertEqual(mark_orders_paid(SESSION_ID), 0)
        self.assertFalse(Order.objects.get().is_paid)

    def test_blank_session_id_is_a_no_op(self):
        """Orders with no session id must not be swept up by a blank lookup."""
        self._order(session_id='')
        self.assertEqual(mark_orders_paid(''), 0)
        self.assertFalse(Order.objects.get().is_paid)

    def test_failed_marks_pending_orders_only(self):
        self._order()
        paid = self._order()
        mark_orders_paid(SESSION_ID)
        Order.objects.filter(id=paid.id).update(payment_status=Order.PAYMENT_PAID)
        mark_orders_failed(SESSION_ID)
        self.assertFalse(
            Order.objects.filter(payment_status=Order.PAYMENT_FAILED).exists())


@override_settings(STRIPE_ENABLED=True, STRIPE_SECRET_KEY='sk_test_x')
class CheckoutSuccessTests(StoreTestCase):

    def setUp(self):
        super().setUp()
        self.login()
        self.set_cart({str(self.product.id): 1})
        Order.objects.create(
            customer=self.customer, product=self.product, price=400,
            quantity=1, stripe_session_id=SESSION_ID,
            payment_status=Order.PAYMENT_PENDING)

    def _visit(self, payment_status='paid'):
        fake = MagicMock()
        # A real StripeObject, not a dict — it does NOT support .get(), so this
        # mock exercises the same access path production hits.
        fake.checkout.Session.retrieve.return_value = StripeObject.construct_from({
            'id': SESSION_ID,
            'object': 'checkout.session',
            'payment_status': payment_status,
            'payment_intent': 'pi_success',
        }, 'sk_test')
        with patch('store.views.payments.get_stripe', return_value=fake):
            return self.client.get(
                reverse('checkout_success'), {'session_id': SESSION_ID})

    def test_marks_the_order_paid(self):
        response = self._visit()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Order.objects.get().is_paid)

    def test_clears_the_cart_once_paid(self):
        self._visit()
        self.assertEqual(self.get_cart(), {})

    def test_unpaid_session_leaves_order_and_cart_alone(self):
        self._visit(payment_status='unpaid')
        self.assertFalse(Order.objects.get().is_paid)
        self.assertEqual(self.get_cart(), {str(self.product.id): 1})

    def test_missing_session_id_redirects_to_orders(self):
        response = self.client.get(reverse('checkout_success'))
        self.assertRedirects(response, '/orders/')


# ---------------------------------------------------------------------------
# Webhook — the security-critical surface
# ---------------------------------------------------------------------------

@override_settings(STRIPE_ENABLED=True, STRIPE_SECRET_KEY='sk_test_x',
                   STRIPE_WEBHOOK_SECRET=WEBHOOK_SECRET)
class WebhookTests(StoreTestCase):

    def setUp(self):
        super().setUp()
        self.order = Order.objects.create(
            customer=self.customer, product=self.product, price=400,
            quantity=1, stripe_session_id=SESSION_ID,
            payment_status=Order.PAYMENT_PENDING)
        self.url = reverse('stripe_webhook')

    def _event(self, event_type='checkout.session.completed',
               payment_status='paid'):
        # Shaped like a real Stripe event, including the top-level "object"
        # field the SDK reads to tell v1 and v2 events apart.
        return json.dumps({
            'id': 'evt_test',
            'object': 'event',
            'type': event_type,
            'data': {'object': {
                'id': SESSION_ID,
                'object': 'checkout.session',
                'payment_status': payment_status,
                'payment_intent': 'pi_hook',
            }},
        }).encode()

    def _post(self, payload, signature=None):
        return self.client.post(
            self.url, data=payload, content_type='application/json',
            HTTP_STRIPE_SIGNATURE=signature if signature is not None
            else stripe_signature(payload, WEBHOOK_SECRET))

    def test_valid_event_marks_order_paid(self):
        response = self._post(self._event())
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)
        self.assertEqual(self.order.stripe_payment_intent, 'pi_hook')

    def test_forged_signature_is_rejected(self):
        response = self._post(self._event(), signature='t=1,v1=deadbeef')
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_missing_signature_is_rejected(self):
        response = self._post(self._event(), signature='')
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_signature_from_the_wrong_secret_is_rejected(self):
        payload = self._event()
        response = self._post(
            payload, signature=stripe_signature(payload, 'whsec_wrongsecret'))
        self.assertEqual(response.status_code, 400)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_tampered_payload_is_rejected(self):
        """Signature computed over a different body must not validate."""
        signature = stripe_signature(self._event(), WEBHOOK_SECRET)
        tampered = self._event(payment_status='paid').replace(
            SESSION_ID.encode(), b'cs_attacker_session')
        response = self._post(tampered, signature=signature)
        self.assertEqual(response.status_code, 400)

    def test_replayed_event_is_harmless(self):
        payload = self._event()
        self._post(payload)
        response = self._post(payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Order.objects.filter(payment_status=Order.PAYMENT_PAID).count(), 1)

    def test_completed_but_unpaid_session_does_not_mark_paid(self):
        self._post(self._event(payment_status='unpaid'))
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def _refund_event(self, payment_intent='pi_hook'):
        """A charge.refunded event — a Charge, not a Session."""
        return json.dumps({
            'id': 'evt_refund',
            'object': 'event',
            'type': 'charge.refunded',
            'data': {'object': {
                'id': 'ch_test',
                'object': 'charge',
                'payment_intent': payment_intent,
                'refunded': True,
            }},
        }).encode()

    def test_refund_event_restocks_and_marks_refunded(self):
        self.product.stock = 10
        self.product.save()
        self._post(self._event())          # pay first
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 9)

        response = self._post(self._refund_event())

        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PAYMENT_REFUNDED)
        self.assertEqual(self.product.stock, 10)

    def test_refund_for_an_unknown_payment_intent_is_ignored(self):
        self._post(self._event())
        response = self._post(self._refund_event(payment_intent='pi_other'))
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertTrue(self.order.is_paid)

    def test_expired_session_marks_order_failed(self):
        self._post(self._event(event_type='checkout.session.expired'))
        self.order.refresh_from_db()
        self.assertEqual(self.order.payment_status, Order.PAYMENT_FAILED)

    def test_unknown_event_type_is_acknowledged_and_ignored(self):
        response = self._post(self._event(event_type='invoice.created'))
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertFalse(self.order.is_paid)

    def test_get_requests_are_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)

    def test_webhook_needs_no_csrf_token(self):
        """Stripe cannot send a CSRF token — the endpoint must not demand one."""
        from django.test import Client
        payload = self._event()
        response = Client(enforce_csrf_checks=True).post(
            self.url, data=payload, content_type='application/json',
            HTTP_STRIPE_SIGNATURE=stripe_signature(payload, WEBHOOK_SECRET))
        self.assertEqual(response.status_code, 200)

    def test_slashless_url_is_accepted(self):
        """An endpoint configured without the trailing slash must still work.

        APPEND_SLASH cannot redirect a POST without dropping the body, so it
        raises a 500 rather than reaching the view. That turned a one-character
        typo in the Stripe endpoint URL into orders that were paid for but
        never fulfilled, so both spellings are routed.
        """
        payload = self._event()
        response = self.client.post(
            '/stripe/webhook', data=payload,
            content_type='application/json',
            HTTP_STRIPE_SIGNATURE=stripe_signature(payload, WEBHOOK_SECRET))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Order.objects.get(pk=self.order.pk).payment_status,
            Order.PAYMENT_PAID)


@override_settings(STRIPE_ENABLED=True, STRIPE_SECRET_KEY='sk_test_x',
                   STRIPE_WEBHOOK_SECRET='')
class WebhookUnconfiguredTests(StoreTestCase):

    def test_rejects_events_when_no_signing_secret_is_set(self):
        """Without a secret nothing can be verified, so nothing is trusted."""
        response = self.client.post(
            reverse('stripe_webhook'), data=b'{}',
            content_type='application/json')
        self.assertEqual(response.status_code, 400)
