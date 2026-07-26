"""Shared fixtures for the store test suite."""

from django.test import TestCase

from store.models.categories import Category
from store.models.customers import Customer
from store.models.products import Products

PASSWORD = 'testpass123'


class StoreTestCase(TestCase):
    """Base case with a catalogue and a registered customer already in place."""

    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(name='Gorras')
        self.other_category = Category.objects.create(name='Insignias')

        self.product = Products.objects.create(
            name='Gorra Naval Oficial',
            price=400,
            category=self.category,
            description='Gorra bordada de oficial.',
        )
        self.cheap_product = Products.objects.create(
            name='Pin Ancla Dorada',
            price=25,
            category=self.other_category,
            description='Pin de solapa.',
        )

        self.customer = Customer(
            first_name='Ana',
            last_name='Marina',
            phone='5551234567',
            email='ana@example.com',
            password=PASSWORD,
        )
        # register() hashes the password before saving.
        self.customer.register()

    # --- helpers -----------------------------------------------------------

    def login(self):
        """Log the test customer in through the real login view."""
        response = self.client.post('/login/', {
            'email': self.customer.email,
            'password': PASSWORD,
        })
        self.assertEqual(
            self.client.session.get('customer'), self.customer.id,
            'login() helper failed — the session has no customer',
        )
        return response

    def set_cart(self, cart):
        """Write a cart straight into the session."""
        session = self.client.session
        session['cart'] = cart
        session.save()

    def get_cart(self):
        return self.client.session.get('cart', {})
