from django.contrib import admin
from .models import Category, Customer, Products, Order

admin.site.register(Category)
admin.site.register(Customer)
admin.site.register(Products)
admin.site.register(Order)
