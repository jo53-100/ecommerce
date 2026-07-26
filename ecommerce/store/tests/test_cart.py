"""Cart behaviour — the session dict and the helpers that read it."""

from store.payments import build_cart_items, cart_total, parse_cart_key

from .base import StoreTestCase


class CartMutationTests(StoreTestCase):
    """Adding and removing goes through the Index POST handler."""

    def test_add_product_to_empty_cart(self):
        self.client.post('/', {'product': str(self.product.id)})
        self.assertEqual(self.get_cart(), {str(self.product.id): 1})

    def test_adding_twice_increments_quantity(self):
        self.client.post('/', {'product': str(self.product.id)})
        self.client.post('/', {'product': str(self.product.id)})
        self.assertEqual(self.get_cart()[str(self.product.id)], 2)

    def test_add_with_explicit_quantity(self):
        self.client.post('/', {'product': str(self.product.id), 'qty': '3'})
        self.assertEqual(self.get_cart()[str(self.product.id)], 3)

    def test_add_with_invalid_quantity_falls_back_to_one(self):
        self.client.post('/', {'product': str(self.product.id), 'qty': 'abc'})
        self.assertEqual(self.get_cart()[str(self.product.id)], 1)

    def test_remove_decrements_quantity(self):
        self.set_cart({str(self.product.id): 3})
        self.client.post('/', {'product': str(self.product.id), 'remove': 'True'})
        self.assertEqual(self.get_cart()[str(self.product.id)], 2)

    def test_removing_last_unit_drops_the_key(self):
        self.set_cart({str(self.product.id): 1})
        self.client.post('/', {'product': str(self.product.id), 'remove': 'True'})
        self.assertNotIn(str(self.product.id), self.get_cart())

    def test_remove_all_clears_the_line(self):
        self.set_cart({str(self.product.id): 5})
        self.client.post('/', {
            'product': str(self.product.id), 'remove_all': 'True'})
        self.assertNotIn(str(self.product.id), self.get_cart())

    def test_colour_variants_are_separate_lines(self):
        self.client.post('/', {'product': str(self.product.id), 'color': 'navy'})
        self.client.post('/', {'product': str(self.product.id), 'color': 'khaki'})
        cart = self.get_cart()
        self.assertIn(f'{self.product.id}_navy', cart)
        self.assertIn(f'{self.product.id}_khaki', cart)

    def test_buy_now_goes_straight_to_checkout(self):
        self.login()
        response = self.client.post('/', {
            'product': str(self.product.id), 'buy_now': '1'})
        self.assertRedirects(response, '/check-out/')


class CartKeyParsingTests(StoreTestCase):

    def test_plain_key(self):
        self.assertEqual(parse_cart_key('12'), ('12', None))

    def test_key_with_colour(self):
        self.assertEqual(parse_cart_key('12_navy'), ('12', 'navy'))


class BuildCartItemsTests(StoreTestCase):
    """build_cart_items is what prices every order — it must be strict."""

    def test_resolves_products_and_prices_from_the_database(self):
        items = build_cart_items({str(self.product.id): 2})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['unit_price'], self.product.price)
        self.assertEqual(items[0]['subtotal'], self.product.price * 2)

    def test_empty_cart_returns_nothing(self):
        self.assertEqual(build_cart_items({}), [])
        self.assertEqual(build_cart_items(None), [])

    def test_unknown_product_id_is_skipped(self):
        """A stale cookie referencing a deleted product must not crash."""
        items = build_cart_items({'999999': 1, str(self.product.id): 1})
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['product'].id, self.product.id)

    def test_non_positive_quantities_are_skipped(self):
        items = build_cart_items({str(self.product.id): 0})
        self.assertEqual(items, [])
        items = build_cart_items({str(self.product.id): -5})
        self.assertEqual(items, [])

    def test_garbage_quantity_is_skipped(self):
        self.assertEqual(build_cart_items({str(self.product.id): 'abc'}), [])

    def test_total_sums_every_line(self):
        items = build_cart_items({
            str(self.product.id): 2,        # 400 * 2 = 800
            str(self.cheap_product.id): 4,  # 25 * 4  = 100
        })
        self.assertEqual(cart_total(items), 900)
