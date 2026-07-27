"""Smoke and behaviour tests for the back-office dashboard.

Two things are worth pinning here: every staff page renders (they are pure
aggregation views, so a bad field name only shows up at render time), and the
inventory actually moves when a product transaction is recorded.
"""
import datetime as dt
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from clinic.forms import RestockForm, TransactionForm
from clinic.models import Employee, Expense, Product, ServiceType, Transaction

# The dashboard aggregates a hardcoded year; tests must use it or see zeroes.
from clinic.views import YEAR


class StaffPagesTest(TestCase):
    """Every back-office page renders for staff and is closed to everyone else."""

    PAGES = ['clinic:dashboard', 'clinic:movimiento_nuevo',
             'clinic:empleada_nueva', 'clinic:gasto_nuevo', 'clinic:inventario']

    def setUp(self):
        self.staff = User.objects.create_user(
            'boss', 'boss@example.com', 'pw', is_staff=True)

    def test_pages_render_for_staff(self):
        self.client.force_login(self.staff)
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_pages_reject_anonymous(self):
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                # staff_member_required bounces to the admin login.
                self.assertEqual(response.status_code, 302)
                self.assertIn('/admin/login/', response['Location'])

    def test_non_staff_user_is_rejected(self):
        User.objects.create_user('shopper', 'shopper@example.com', 'pw')
        self.client.login(username='shopper', password='pw')
        response = self.client.get(reverse('clinic:dashboard'))
        self.assertEqual(response.status_code, 302)


class DashboardNumbersTest(TestCase):
    """The KPI row is derived, not stored — check the arithmetic."""

    def setUp(self):
        self.staff = User.objects.create_user(
            'boss', 'boss@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)
        self.service = ServiceType.objects.create(
            name='Podologia general', category='podologia', price=Decimal('500'))
        self.employee = Employee.objects.create(
            name='Ana', role='podologa',
            base_salary_weekly=Decimal('1000'), commission_rate=Decimal('0.10'))

    def test_profit_is_income_minus_expenses(self):
        day = dt.date(YEAR, 3, 10)
        Transaction.objects.create(date=day, kind='service', amount=Decimal('500'),
                                   service_type=self.service, employee=self.employee)
        Transaction.objects.create(date=day, kind='product_sale', amount=Decimal('200'))
        Expense.objects.create(date=day, category='rent', amount=Decimal('300'))

        kpi = self.client.get(reverse('clinic:dashboard')).context['kpi']
        self.assertEqual(kpi['income'], Decimal('700'))
        self.assertEqual(kpi['expenses'], Decimal('300'))
        self.assertEqual(kpi['profit'], Decimal('400'))
        self.assertEqual(kpi['services'], 1)

    def test_tips_are_not_counted_as_income(self):
        """A tip is the employee's money, not the clinic's revenue."""
        Transaction.objects.create(date=dt.date(YEAR, 3, 10), kind='tip',
                                   amount=Decimal('100'))
        kpi = self.client.get(reverse('clinic:dashboard')).context['kpi']
        self.assertEqual(kpi['income'], Decimal('0'))

    def test_commission_is_derived_from_service_sales(self):
        Transaction.objects.create(date=dt.date(YEAR, 3, 10), kind='service',
                                   amount=Decimal('500'), service_type=self.service,
                                   employee=self.employee)
        payroll = self.client.get(reverse('clinic:dashboard')).context['payroll']
        row = next(r for r in payroll if r['name'] == 'Ana')
        self.assertAlmostEqual(row['commission'], 50.0)

    def test_month_filter_scopes_the_kpis(self):
        Transaction.objects.create(date=dt.date(YEAR, 1, 5), kind='service',
                                   amount=Decimal('100'), service_type=self.service)
        Transaction.objects.create(date=dt.date(YEAR, 2, 5), kind='service',
                                   amount=Decimal('900'), service_type=self.service)
        kpi = self.client.get(reverse('clinic:dashboard'), {'month': 2}).context['kpi']
        self.assertEqual(kpi['income'], Decimal('900'))

    def test_garbage_month_parameter_does_not_500(self):
        response = self.client.get(reverse('clinic:dashboard'), {'month': 'abril'})
        self.assertEqual(response.status_code, 200)


class InventoryMovementTest(TestCase):
    """Stock is the point of the inventory page — verify it actually moves."""

    def setUp(self):
        self.product = Product.objects.create(
            name='Urea', for_sale=True,
            unit_cost=Decimal('40'), sale_price=Decimal('120'), stock=10)

    def _tx_form(self, **overrides):
        data = {
            'date': dt.date(YEAR, 3, 10), 'kind': 'product_sale',
            'product': self.product.pk, 'cantidad': 3,
            'payment_method': 'cash', 'note': '',
        }
        data.update(overrides)
        return TransactionForm(data)

    def test_selling_a_product_decrements_stock(self):
        form = self._tx_form()
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)

    def test_amount_is_derived_from_sale_price_when_left_blank(self):
        form = self._tx_form()
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        self.assertEqual(tx.amount, Decimal('360'))  # 120 x 3

    def test_internal_use_is_priced_at_cost(self):
        form = self._tx_form(kind='product_use')
        self.assertTrue(form.is_valid(), form.errors)
        tx = form.save()
        self.assertEqual(tx.amount, Decimal('120'))  # 40 x 3
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 7)

    def test_explicit_amount_overrides_the_derived_price(self):
        form = self._tx_form(amount='300')
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().amount, Decimal('300'))

    def test_product_movement_requires_a_product(self):
        form = self._tx_form(product='')
        self.assertFalse(form.is_valid())
        self.assertIn('product', form.errors)

    def test_service_without_amount_is_rejected(self):
        """Services have no price to derive from, so the amount is mandatory."""
        form = TransactionForm({'date': dt.date(YEAR, 3, 10), 'kind': 'service',
                                'payment_method': 'cash'})
        self.assertFalse(form.is_valid())
        self.assertIn('amount', form.errors)

    def test_restock_adds_units(self):
        form = RestockForm({'product': self.product.pk, 'units': 5})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 15)

    def test_service_transaction_leaves_stock_alone(self):
        service = ServiceType.objects.create(name='Masaje', category='masaje')
        form = TransactionForm({'date': dt.date(YEAR, 3, 10), 'kind': 'service',
                                'service_type': service.pk, 'amount': '400',
                                'payment_method': 'card'})
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
