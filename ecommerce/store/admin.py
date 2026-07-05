from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Category, Customer, Products, Order


@admin.register(Products)
class ProductsAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price')
    list_filter = ('category',)
    search_fields = ('name', 'description')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'phone')
    search_fields = ('first_name', 'last_name', 'email')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'status_badge', 'product', 'customer', 'quantity',
        'price', 'tracking_number', 'address', 'date',
    )
    list_filter = ('status', 'date')
    search_fields = (
        'customer__email', 'customer__first_name', 'customer__last_name',
        'product__name', 'tracking_number', 'address',
    )
    list_editable = ('tracking_number',)
    list_per_page = 50
    actions = ('mark_as_shipped', 'mark_as_delivered', 'mark_as_new')

    @admin.display(description='Status', ordering='status')
    def status_badge(self, obj):
        colors = {
            Order.NEW: '#d4a017',        # amber
            Order.SHIPPED: '#3b82c4',    # blue
            Order.DELIVERED: '#63a05a',  # green
        }
        color = colors.get(obj.status, '#888')
        return format_html(
            '<b style="color:{}">&#9679; {}</b>',
            color, obj.get_status_display().split(' — ')[0].upper(),
        )

    @admin.action(description='Mark selected orders as SHIPPED (sent)')
    def mark_as_shipped(self, request, queryset):
        updated = queryset.update(status=Order.SHIPPED, shipped_at=timezone.now().date())
        self.message_user(request, f'{updated} order(s) marked as shipped.')

    @admin.action(description='Mark selected orders as DELIVERED')
    def mark_as_delivered(self, request, queryset):
        updated = queryset.update(status=Order.DELIVERED)
        self.message_user(request, f'{updated} order(s) marked as delivered.')

    @admin.action(description='Reset selected orders to NEW')
    def mark_as_new(self, request, queryset):
        updated = queryset.update(status=Order.NEW, shipped_at=None)
        self.message_user(request, f'{updated} order(s) reset to new.')
