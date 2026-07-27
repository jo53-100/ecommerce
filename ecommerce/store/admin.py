from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html

from .models import Category, Customer, Products, Order


@admin.register(Products)
class ProductsAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'unit_cost',
                    'stock_badge', 'track_inventory', 'for_sale')
    list_filter = ('category', 'for_sale', 'track_inventory')
    search_fields = ('name', 'description')
    list_editable = ('track_inventory', 'for_sale')

    @admin.display(description='Stock', ordering='stock')
    def stock_badge(self, obj):
        if not obj.track_inventory:
            return format_html('<span style="color:#888">not tracked</span>')
        color = '#63a05a' if obj.stock > 5 else (
            '#d4a017' if obj.stock > 0 else '#ef4444')
        return format_html('<b style="color:{}">{}</b>', color, obj.stock)


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
        'id', 'payment_badge', 'status_badge', 'product', 'customer',
        'quantity', 'price', 'tracking_number', 'ship_to', 'date',
    )
    list_filter = ('payment_status', 'status', 'date')
    search_fields = (
        'customer__email', 'customer__first_name', 'customer__last_name',
        'product__name', 'tracking_number', 'city', 'state', 'zip_code',
        'stripe_session_id', 'stripe_payment_intent',
    )
    list_editable = ('tracking_number',)
    list_per_page = 50
    actions = ('mark_as_shipped', 'mark_as_delivered', 'mark_as_new')
    # Written by Stripe, not by hand — editing them would desync the records.
    readonly_fields = ('stripe_session_id', 'stripe_payment_intent', 'paid_at')

    @admin.display(description='Ship to')
    def ship_to(self, obj):
        return obj.city_line or obj.recipient_name or '—'

    @admin.display(description='Payment', ordering='payment_status')
    def payment_badge(self, obj):
        colors = {
            Order.PAYMENT_PAID: '#63a05a',      # green
            Order.PAYMENT_PENDING: '#d4a017',   # amber
            Order.PAYMENT_FAILED: '#ef4444',    # red
            Order.PAYMENT_REFUNDED: '#888',     # grey
        }
        color = colors.get(obj.payment_status, '#888')
        return format_html(
            '<b style="color:{}">&#9679; {}</b>',
            color, obj.get_payment_status_display().split(' — ')[0].upper(),
        )

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
