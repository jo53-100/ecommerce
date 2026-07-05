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

    product = models.ForeignKey(Products, on_delete=models.CASCADE)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    price = models.IntegerField()
    phone = models.CharField(max_length=50, default='', blank=True)
    date = models.DateField(default=datetime.date.today)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=NEW)
    tracking_number = models.CharField(max_length=60, blank=True, default='')
    shipped_at = models.DateField(null=True, blank=True)

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
