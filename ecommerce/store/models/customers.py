from django.db import models
from django.contrib.auth.hashers import make_password

class Customer(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=10)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=100)

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
