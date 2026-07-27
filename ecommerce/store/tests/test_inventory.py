"""Inventory control and Decimal money.

The rule these tests exist to defend: stock moves when, and only when, money
moves. It is decremented in the same transaction that marks an order paid, put
back on refund, and never moved twice for the same event — Stripe retries
webhooks, and the success page can confirm a payment the webhook already did.
"""

from decimal import Decimal

from django.urls import reverse

from store.models.orders import Order
from store.models.products import Products
from store.payments import (
    build_cart_items,
    cart_total,
    mark_orders_paid,
    mark_orders_refunded,
    out_of_stock_items,
    to_stripe_amount,
)

from .base import StoreTestCase

SESSION_ID = 'cs_test_inventory'

ADDRESS = {
    'recipient_name': 'Ana Marina',
    'street_address': 'Calle Naval 123',
    'city': 'Veracruz',
    'state': 'Veracruz',
    'zip_code': '91700',
    'country': 'México',
    'phone': '5551234567',
}


class StripeAmountConversionTests(StoreTestCase):
    """Stripe only accepts integer centavos; everything else stays Decimal."""

    def test_whole_pesos_convert_to_centavos(self):
        self.assertEqual(to_stripe_amount(Decimal('400.00')), 40000)

    def test_centavos_survive_the_conversion(self):
        self.assertEqual(to_stripe_amount(Decimal('99.99')), 9999)
        self.assertEqual(to_stripe_amount(Decimal('0.50')), 50)

    def test_plain_integers_still_work(self):
        self.assertEqual(to_stripe_amount(400), 40000)

    def test_half_centavo_rounds_up_not_to_even(self):
        """ROUND_HALF_UP, so 0.005 goes up predictably rather than to even."""
        self.assertEqual(to_stripe_amount(Decimal('1.005')), 101)
        self.assertEqual(to_stripe_amount(Decimal('1.015')), 102)

    def test_result_is_an_int(self):
        self.assertIsInstance(to_stripe_amount(Decimal('12.34')), int)


class DecimalMoneyTests(StoreTestCase):

    def test_price_keeps_centavos_through_the_database(self):
        self.product.price = Decimal('349.99')
        self.product.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal('349.99'))

    def test_cart_subtotal_is_decimal_not_float(self):
        self.product.price = Decimal('0.10')
        self.product.save()
        items = build_cart_items({str(self.product.id): 3})
        # 0.10 * 3 is exactly 0.30 in Decimal; in float it is 0.30000000000000004.
        self.assertEqual(items[0]['subtotal'], Decimal('0.30'))

    def test_empty_cart_totals_decimal_zero(self):
        self.assertEqual(cart_total([]), Decimal('0.00'))

    def test_price_split_for_the_storefront_display(self):
        self.product.price = Decimal('349.05')
        self.assertEqual(self.product.price_units, 349)
        self.assertEqual(self.product.price_cents, '05')

    def test_price_split_pads_whole_amounts(self):
        self.product.price = Decimal('400.00')
        self.assertEqual(self.product.price_cents, '00')


class StockAvailabilityTests(StoreTestCase):

    def test_product_with_stock_can_supply(self):
        self.product.stock = 5
        self.assertTrue(self.product.can_supply(5))
        self.assertFalse(self.product.can_supply(6))

    def test_untracked_product_can_always_supply(self):
        self.product.stock = 0
        self.product.track_inventory = False
        self.assertTrue(self.product.can_supply(999))
        self.assertTrue(self.product.in_stock)

    def test_cart_flags_the_unavailable_line(self):
        self.product.stock = 1
        self.product.save()
        items = build_cart_items({str(self.product.id): 4})
        self.assertFalse(items[0]['available'])
        self.assertEqual(len(out_of_stock_items(items)), 1)

    def test_internal_supplies_are_hidden_from_the_storefront(self):
        self.product.for_sale = False
        self.product.save()
        listed = Products.get_all_products()
        self.assertNotIn(self.product, listed)
        self.assertIn(self.cheap_product, listed)


class CheckoutStockGateTests(StoreTestCase):
    """Nothing may be sold that cannot be shipped."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_checkout_is_refused_when_stock_is_short(self):
        self.product.stock = 2
        self.product.save()
        self.set_cart({str(self.product.id): 3})

        response = self.client.post('/check-out/', ADDRESS)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0,
                         'a refused checkout must not leave orders behind')

    def test_the_refusal_names_the_offending_product(self):
        self.product.stock = 0
        self.product.save()
        self.set_cart({str(self.product.id): 1})

        response = self.client.post('/check-out/', ADDRESS)

        self.assertContains(response, self.product.name, status_code=400)

    def test_exactly_enough_stock_is_allowed_through(self):
        self.product.stock = 3
        self.product.save()
        self.set_cart({str(self.product.id): 3})

        self.client.post('/check-out/', ADDRESS)

        self.assertEqual(Order.objects.count(), 1)

    def test_untracked_product_bypasses_the_gate(self):
        self.product.stock = 0
        self.product.track_inventory = False
        self.product.save()
        self.set_cart({str(self.product.id): 50})

        self.client.post('/check-out/', ADDRESS)

        self.assertEqual(Order.objects.count(), 1)

    def test_unpaid_orders_do_not_consume_stock(self):
        """Without Stripe configured, orders are pending — stock must not move."""
        self.set_cart({str(self.product.id): 2})
        starting = self.product.stock

        self.client.post('/check-out/', ADDRESS)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, starting)


class StockMovesWithMoneyTests(StoreTestCase):

    def _order(self, qty=1, product=None, session_id=SESSION_ID,
               status=Order.PAYMENT_PENDING, payment_intent=''):
        return Order.objects.create(
            customer=self.customer, product=product or self.product,
            price=Decimal('400.00'), quantity=qty,
            stripe_session_id=session_id, stripe_payment_intent=payment_intent,
            payment_status=status)

    def test_paying_decrements_stock(self):
        self.product.stock = 10
        self.product.save()
        self._order(qty=3)

        mark_orders_paid(SESSION_ID, 'pi_1')

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)

    def test_every_line_in_the_session_is_decremented(self):
        self.product.stock = 10
        self.product.save()
        self.cheap_product.stock = 4
        self.cheap_product.save()
        self._order(qty=2)
        self._order(qty=1, product=self.cheap_product)

        mark_orders_paid(SESSION_ID, 'pi_1')

        self.product.refresh_from_db()
        self.cheap_product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(self.cheap_product.stock, 3)

    def test_a_replayed_webhook_does_not_decrement_twice(self):
        """The whole reason the update is locked and status-filtered."""
        self.product.stock = 10
        self.product.save()
        self._order(qty=3)

        mark_orders_paid(SESSION_ID, 'pi_1')
        mark_orders_paid(SESSION_ID, 'pi_1')

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)

    def test_untracked_products_are_never_decremented(self):
        self.product.track_inventory = False
        self.product.stock = 10
        self.product.save()
        self._order(qty=3)

        mark_orders_paid(SESSION_ID, 'pi_1')

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_refund_puts_the_stock_back(self):
        self.product.stock = 10
        self.product.save()
        self._order(qty=3)
        mark_orders_paid(SESSION_ID, 'pi_refund')

        self.assertEqual(mark_orders_refunded('pi_refund'), 1)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(Order.objects.get().payment_status,
                         Order.PAYMENT_REFUNDED)

    def test_refund_is_idempotent(self):
        self.product.stock = 10
        self.product.save()
        self._order(qty=3)
        mark_orders_paid(SESSION_ID, 'pi_refund')

        mark_orders_refunded('pi_refund')
        self.assertEqual(mark_orders_refunded('pi_refund'), 0)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_refunding_an_unpaid_order_does_nothing(self):
        self.product.stock = 10
        self.product.save()
        self._order(qty=3, payment_intent='pi_never_paid')

        self.assertEqual(mark_orders_refunded('pi_never_paid'), 0)

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)

    def test_blank_payment_intent_is_ignored(self):
        """Otherwise a blank intent would match every order that has none."""
        self._order()
        self.assertEqual(mark_orders_refunded(''), 0)

    def test_stock_can_be_driven_to_zero(self):
        self.product.stock = 3
        self.product.save()
        self._order(qty=3)

        mark_orders_paid(SESSION_ID, 'pi_1')

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 0)
        self.assertFalse(self.product.in_stock)
