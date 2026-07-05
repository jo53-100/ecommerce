from django.db import models
from django.contrib.auth.hashers import make_password
from .address import AddressMixin

class Customer(AddressMixin):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=20)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    # Save customer
    def register(self):
        # If you want hashed password:
        self.password = make_password(self.password)
        self.save()

    @staticmethod
    def get_customer_by_email(email):
        try:
            return Customer.objects.get(email=email)
        except Customer.DoesNotExist:
            return False

    def isExists(self):
        return Customer.objects.filter(email=self.email).exists()

    class Meta:
        verbose_name_plural = "Customers"
