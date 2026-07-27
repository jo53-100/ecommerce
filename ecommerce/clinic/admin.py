from django.contrib import admin
from django.db.models import Sum, Count
from .models import Employee, ServiceType, Product, Client, Transaction, Expense


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "base_salary_weekly", "commission_rate", "active")
    list_filter = ("role", "active")


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "active")
    list_filter = ("category", "active")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "for_sale", "unit_cost", "sale_price", "stock")
    list_filter = ("for_sale",)
    search_fields = ("name",)


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "age", "occupation", "phone", "diabetic")
    list_filter = ("diabetic",)
    search_fields = ("name", "phone")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "kind", "service_type", "product", "employee", "amount", "payment_method", "walk_in")
    list_filter = ("kind", "payment_method", "walk_in", "is_imported_aggregate", "employee")
    date_hierarchy = "date"          # gives drill-down por ano/mes/dia = conteos diario/semanal/mensual
    search_fields = ("note",)
    autocomplete_fields = ("service_type", "product", "client")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "category", "amount", "note")
    list_filter = ("category",)
    date_hierarchy = "date"
