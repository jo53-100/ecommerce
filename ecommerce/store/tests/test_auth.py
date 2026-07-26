"""Signup, login, logout, and access control."""

from urllib.parse import quote

from store.models.customers import Customer

from .base import PASSWORD, StoreTestCase


class SignupTests(StoreTestCase):

    def test_signup_creates_customer(self):
        response = self.client.post('/signup/', {
            'firstname': 'Pedro',
            'lastname': 'Navarro',
            'phone': '5559876543',
            'email': 'pedro@example.com',
            'password': 'securepass',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Customer.objects.filter(email='pedro@example.com').exists())

    def test_signup_hashes_the_password(self):
        """The raw password must never be what lands in the database."""
        self.client.post('/signup/', {
            'firstname': 'Pedro',
            'lastname': 'Navarro',
            'phone': '5559876543',
            'email': 'pedro@example.com',
            'password': 'securepass',
        })
        customer = Customer.objects.get(email='pedro@example.com')
        self.assertNotEqual(customer.password, 'securepass')
        self.assertTrue(len(customer.password) > 30)

    def test_signup_rejects_duplicate_email(self):
        response = self.client.post('/signup/', {
            'firstname': 'Otra',
            'lastname': 'Persona',
            'phone': '5551112222',
            'email': self.customer.email,  # already taken
            'password': 'securepass',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Already Registered')
        self.assertEqual(
            Customer.objects.filter(email=self.customer.email).count(), 1)

    def test_signup_rejects_short_password(self):
        response = self.client.post('/signup/', {
            'firstname': 'Pedro',
            'lastname': 'Navarro',
            'phone': '5559876543',
            'email': 'pedro@example.com',
            'password': 'abc',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Customer.objects.filter(email='pedro@example.com').exists())


class LoginTests(StoreTestCase):

    def test_login_with_valid_credentials(self):
        self.client.post('/login/', {
            'email': self.customer.email, 'password': PASSWORD})
        self.assertEqual(self.client.session.get('customer'), self.customer.id)

    def test_login_with_wrong_password_fails(self):
        response = self.client.post('/login/', {
            'email': self.customer.email, 'password': 'wrongpassword'})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get('customer'))

    def test_login_with_unknown_email_fails(self):
        response = self.client.post('/login/', {
            'email': 'nobody@example.com', 'password': PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.client.session.get('customer'))

    def test_logout_clears_session(self):
        self.login()
        self.client.get('/logout/')
        self.assertIsNone(self.client.session.get('customer'))

    def test_login_honours_safe_return_url(self):
        response = self.client.post('/login/?return_url=/cart/', {
            'email': self.customer.email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/cart/')

    def test_login_ignores_offsite_return_url(self):
        """Open-redirect guard: an external return_url must not be honoured."""
        response = self.client.post('/login/?return_url=https://evil.example', {
            'email': self.customer.email, 'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('evil.example', response.url)


class AccessControlTests(StoreTestCase):
    """Protected pages must bounce anonymous visitors to login."""

    PROTECTED = ['/cart/', '/orders/', '/account/', '/check-out/']

    def test_protected_pages_redirect_when_logged_out(self):
        for path in self.PROTECTED:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn('/login/', response.url)

    def test_redirect_preserves_intended_destination(self):
        response = self.client.get('/orders/')
        self.assertIn(f'return_url={quote("/orders/")}', response.url)
