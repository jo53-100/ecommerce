from decimal import Decimal

from django.db import models
from .products import Products
from .customers import Customer
from .address import AddressMixin
import datetime

class Order(AddressMixin):
    NEW = 'new'
    SHIPPED = 'shipped'
    DELIVERED = 'delivered'
    STATUS_CHOICES = [
        (NEW, 'New — awaiting fulfillment'),
        (SHIPPED, 'Shipped — in transit'),
        (DELIVERED, 'Delivered'),
    ]

    # Payment lifecycle, tracked separately from fulfillment status above.
    PAYMENT_PENDING = 'pending'
    PAYMENT_PAID = 'paid'
    PAYMENT_FAILED = 'failed'
    PAYMENT_REFUNDED = 'refunded'
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, 'Pending — awaiting payment'),
        (PAYMENT_PAID, 'Paid'),
        (PAYMENT_FAILED, 'Failed'),
        (PAYMENT_REFUNDED, 'Refunded'),
    ]

    product = models.ForeignKey(Products, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    # Snapshot of the unit price at purchase time, so later catalogue edits do
    # not rewrite what the customer actually paid. Decimal for the same reason
    # as Products.price — see that model's docstring.
    price = models.DecimalField(max_digits=10, decimal_places=2,
                                default=Decimal('0.00'))
    phone = models.CharField(max_length=50, default='', blank=True)
    date = models.DateField(default=datetime.date.today)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=NEW)
    tracking_number = models.CharField(max_length=60, blank=True, default='')
    shipped_at = models.DateField(null=True, blank=True)

    # --- Stripe ---
    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_PENDING)
    # All orders from one checkout share a session id, so the webhook can find
    # them again when Stripe confirms the payment.
    stripe_session_id = models.CharField(
        max_length=255, blank=True, default='', db_index=True)
    stripe_payment_intent = models.CharField(
        max_length=255, blank=True, default='')
    paid_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_paid(self):
        return self.payment_status == self.PAYMENT_PAID

    @property
    def line_total(self):
        return self.price * self.quantity

    def placeOrder(self):
        self.save()

    def mark_shipped(self, tracking_number=''):
        self.status = self.SHIPPED
        self.shipped_at = datetime.date.today()
        if tracking_number:
            self.tracking_number = tracking_number
        self.save()

    def mark_delivered(self):
        self.status = self.DELIVERED
        self.save()

    @staticmethod
    def get_orders_by_customer(customer_id):
        return Order.objects.filter(customer=customer_id).order_by('-date')

    class Meta:
        verbose_name_plural = "Orders"
