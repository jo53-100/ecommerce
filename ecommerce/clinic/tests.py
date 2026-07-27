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
from django.utils import timezone

from clinic.forms import RestockForm, TransactionForm
from store.models.categories import Category
from store.models.customers import Customer
from store.models.orders import Order
from store.models.products import Products
from clinic.models import Employee, Expense, ServiceType, Transaction

# The dashboard defaults to the current year; tests must use it or see zeroes.
from clinic.views import current_year

YEAR = current_year()


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


class OnlineSalesFeedTheDashboardTest(TestCase):
    """Stripe revenue must show up here without anything writing to clinic.*

    store.Order is read directly, so an online sale lands in the finances the
    moment it is paid — no sync step, nothing to fall out of date.
    """

    def setUp(self):
        self.staff = User.objects.create_user(
            'boss', 'boss@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)
        category = Category.objects.create(name='Gorras')
        self.product = Products.objects.create(
            name='Gorra', category=category, price=Decimal('400.00'), stock=10)
        self.customer = Customer(first_name='Ana', last_name='Marina',
                                 email='ana@example.com', password='pw')
        self.customer.register()

    def _order(self, qty=1, status=Order.PAYMENT_PAID, month=3):
        return Order.objects.create(
            customer=self.customer, product=self.product,
            price=Decimal('400.00'), quantity=qty, payment_status=status,
            paid_at=timezone.make_aware(dt.datetime(YEAR, month, 10, 12, 0)))

    def test_paid_online_orders_count_as_income(self):
        self._order(qty=2)
        kpi = self.client.get(reverse('clinic:dashboard')).context['kpi']
        self.assertEqual(kpi['online'], Decimal('800.00'))
        self.assertEqual(kpi['income'], Decimal('800.00'))

    def test_unpaid_orders_are_not_income(self):
        """Money that has not arrived is not revenue."""
        self._order(status=Order.PAYMENT_PENDING)
        kpi = self.client.get(reverse('clinic:dashboard')).context['kpi']
        self.assertEqual(kpi['online'], Decimal('0.00'))

    def test_refunded_orders_are_not_income(self):
        self._order(status=Order.PAYMENT_REFUNDED)
        kpi = self.client.get(reverse('clinic:dashboard')).context['kpi']
        self.assertEqual(kpi['online'], Decimal('0.00'))

    def test_online_and_counter_income_are_added_together(self):
        self._order()                                     # 400 online
        service = ServiceType.objects.create(name='Masaje', category='masaje')
        Transaction.objects.create(date=dt.date(YEAR, 3, 10), kind='service',
                                   service_type=service, amount=Decimal('600'))
        kpi = self.client.get(reverse('clinic:dashboard')).context['kpi']
        self.assertEqual(kpi['counter'], Decimal('600'))
        self.assertEqual(kpi['online'], Decimal('400.00'))
        self.assertEqual(kpi['income'], Decimal('1000.00'))

    def test_online_income_respects_the_month_filter(self):
        self._order(month=1)
        self._order(month=2, qty=3)
        kpi = self.client.get(reverse('clinic:dashboard'),
                              {'month': 2}).context['kpi']
        self.assertEqual(kpi['online'], Decimal('1200.00'))

    def test_store_stock_is_what_the_inventory_panel_shows(self):
        response = self.client.get(reverse('clinic:dashboard'))
        row = next(p for p in response.context['products']
                   if p['name'] == 'Gorra')
        self.assertEqual(row['stock'], 10)
        self.assertTrue(row['tracked'])


class DashboardYearTest(TestCase):
    """The reporting year follows the clock, and can be navigated."""

    def setUp(self):
        self.staff = User.objects.create_user(
            'boss', 'boss@example.com', 'pw', is_staff=True)
        self.client.force_login(self.staff)

    def test_defaults_to_the_current_year(self):
        response = self.client.get(reverse('clinic:dashboard'))
        self.assertEqual(response.context['year'], dt.date.today().year)

    def test_an_explicit_year_is_honoured(self):
        response = self.client.get(reverse('clinic:dashboard'), {'year': 2024})
        self.assertEqual(response.context['year'], 2024)

    def test_garbage_year_falls_back_to_the_current_one(self):
        response = self.client.get(reverse('clinic:dashboard'), {'year': 'dos mil'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['year'], dt.date.today().year)

    def test_out_of_range_month_is_ignored(self):
        response = self.client.get(reverse('clinic:dashboard'), {'month': 99})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context['month'])

    def test_a_year_with_no_data_renders_empty_rather_than_failing(self):
        response = self.client.get(reverse('clinic:dashboard'), {'year': 1999})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['kpi']['income'], Decimal('0.00'))


class InventoryMovementTest(TestCase):
    """Stock is the point of the inventory page — verify it actually moves."""

    def setUp(self):
        category = Category.objects.create(name='Podologia')
        # The catalogue is store.Products — the clinic has no table of its own.
        self.product = Products.objects.create(
            name='Urea', category=category, for_sale=True,
            unit_cost=Decimal('40'), price=Decimal('120'), stock=10)

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
