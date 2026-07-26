"""Checkout without Stripe configured (the fallback / demo path)."""

from django.test import override_settings

from store.models.orders import Order

from .base import StoreTestCase

ADDRESS = {
    'recipient_name': 'Ana Marina',
    'street_address': 'Calle Naval 123',
    'address_line2': 'Depto 4B',
    'city': 'Veracruz',
    'state': 'Veracruz',
    'zip_code': '91700',
    'country': 'México',
    'phone': '5551234567',
}


@override_settings(STRIPE_ENABLED=False, STRIPE_SECRET_KEY='')
class CheckoutFallbackTests(StoreTestCase):

    def setUp(self):
        super().setUp()
        self.login()

    def test_creates_one_order_per_cart_line(self):
        self.set_cart({
            str(self.product.id): 2,
            str(self.cheap_product.id): 1,
        })
        self.client.post('/check-out/', ADDRESS)
        self.assertEqual(Order.objects.count(), 2)

    def test_order_snapshots_price_and_quantity(self):
        self.set_cart({str(self.product.id): 3})
        self.client.post('/check-out/', ADDRESS)
        order = Order.objects.get()
        self.assertEqual(order.price, self.product.price)
        self.assertEqual(order.quantity, 3)
        self.assertEqual(order.line_total, self.product.price * 3)

    def test_order_records_the_shipping_address(self):
        self.set_cart({str(self.product.id): 1})
        self.client.post('/check-out/', ADDRESS)
        order = Order.objects.get()
        self.assertEqual(order.street_address, 'Calle Naval 123')
        self.assertEqual(order.city, 'Veracruz')
        self.assertEqual(order.zip_code, '91700')

    def test_orders_start_unpaid(self):
        """Nothing was charged, so nothing may be marked paid."""
        self.set_cart({str(self.product.id): 1})
        self.client.post('/check-out/', ADDRESS)
        self.assertEqual(Order.objects.get().payment_status,
                         Order.PAYMENT_PENDING)

    def test_cart_is_emptied_after_ordering(self):
        self.set_cart({str(self.product.id): 1})
        self.client.post('/check-out/', ADDRESS)
        self.assertEqual(self.get_cart(), {})

    def test_save_address_updates_the_profile(self):
        self.set_cart({str(self.product.id): 1})
        self.client.post('/check-out/', dict(ADDRESS, save_address='1'))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.city, 'Veracruz')

    def test_profile_untouched_when_save_address_not_ticked(self):
        self.set_cart({str(self.product.id): 1})
        self.client.post('/check-out/', ADDRESS)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.city, '')

    def test_empty_cart_cannot_create_orders(self):
        self.set_cart({})
        response = self.client.post('/check-out/', ADDRESS)
        self.assertRedirects(response, '/cart/')
        self.assertEqual(Order.objects.count(), 0)

    def test_price_is_never_taken_from_the_request(self):
        """POSTing a price must not change what the order records."""
        self.set_cart({str(self.product.id): 1})
        self.client.post('/check-out/', dict(ADDRESS, price='1', amount='1'))
        self.assertEqual(Order.objects.get().price, self.product.price)

    def test_stale_product_in_cart_is_ignored(self):
        self.set_cart({'999999': 2, str(self.product.id): 1})
        self.client.post('/check-out/', ADDRESS)
        self.assertEqual(Order.objects.count(), 1)


class OrderVisibilityTests(StoreTestCase):
    """A customer must only ever see their own orders."""

    def test_orders_page_shows_only_own_orders(self):
        from store.models.customers import Customer

        other = Customer(first_name='Otro', last_name='Cliente',
                         phone='5550000000', email='otro@example.com',
                         password='otherpass')
        other.register()

        Order.objects.create(customer=self.customer, product=self.product,
                             price=400, quantity=1, recipient_name='Mine')
        Order.objects.create(customer=other, product=self.product,
                             price=400, quantity=1, recipient_name='Theirs')

        self.login()
        response = self.client.get('/orders/')
        self.assertContains(response, 'Mine')
        self.assertNotContains(response, 'Theirs')
