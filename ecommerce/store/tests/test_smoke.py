"""Smoke tests: every page renders without blowing up.

These are the cheapest, highest-value tests in the suite. A template typo, a
renamed context variable, or a broken {% url %} tag shows up here immediately.
"""

from django.urls import reverse

from .base import StoreTestCase


class PublicPagesTests(StoreTestCase):
    """Pages a logged-out visitor can reach."""

    def test_store_page_loads(self):
        response = self.client.get('/store/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_store_lists_categories(self):
        response = self.client.get('/store/')
        self.assertContains(response, 'Gorras')
        self.assertContains(response, 'Insignias')

    def test_store_filters_by_category(self):
        response = self.client.get(f'/store/?category={self.category.id}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertNotContains(response, self.cheap_product.name)

    def test_homepage_redirects_to_store(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/store', response.url)

    def test_login_page_loads(self):
        self.assertEqual(self.client.get('/login/').status_code, 200)

    def test_signup_page_loads(self):
        self.assertEqual(self.client.get('/signup/').status_code, 200)

    def test_empty_catalogue_still_renders(self):
        """An empty store must show the empty state, not crash."""
        from store.models.products import Products
        Products.objects.all().delete()
        response = self.client.get('/store/')
        self.assertEqual(response.status_code, 200)


class AuthenticatedPagesTests(StoreTestCase):
    """Pages that require a signed-in customer."""

    def setUp(self):
        super().setUp()
        self.login()

    def test_cart_page_loads(self):
        self.assertEqual(self.client.get('/cart/').status_code, 200)

    def test_orders_page_loads(self):
        self.assertEqual(self.client.get('/orders/').status_code, 200)

    def test_profile_page_loads(self):
        self.assertEqual(self.client.get('/account/').status_code, 200)

    def test_checkout_with_items_loads(self):
        self.set_cart({str(self.product.id): 2})
        response = self.client.get('/check-out/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_checkout_with_empty_cart_redirects_to_cart(self):
        self.set_cart({})
        response = self.client.get('/check-out/')
        self.assertRedirects(response, '/cart/')

    def test_cancel_page_loads(self):
        self.assertEqual(
            self.client.get(reverse('checkout_cancel')).status_code, 200)


class UrlReverseTests(StoreTestCase):
    """Every named route must reverse — catches typos in {% url %} tags."""

    def test_all_named_urls_reverse(self):
        for name in ['homepage', 'store', 'signup', 'login', 'logout', 'cart',
                     'checkout', 'orders', 'profile', 'checkout_success',
                     'checkout_cancel', 'stripe_webhook']:
            with self.subTest(url_name=name):
                self.assertTrue(reverse(name))
