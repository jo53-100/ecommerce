from django.shortcuts import render, redirect
from django.views import View
from store.models.customers import Customer
from store.models.products import Products
from store.models.orders import Order

# Postal-address fields shared by the checkout form, Customer and Order.
ADDRESS_FIELDS = [
    'recipient_name', 'street_address', 'address_line2',
    'city', 'state', 'zip_code', 'country',
]


class CheckOut(View):
    def post(self, request):
        customer_id = request.session.get('customer')
        customer = Customer.objects.get(id=customer_id)

        address = {f: (request.POST.get(f) or '').strip() for f in ADDRESS_FIELDS}
        phone = (request.POST.get('phone') or '').strip()

        # Optionally remember this address on the customer's profile.
        if request.POST.get('save_address'):
            for field, value in address.items():
                setattr(customer, field, value)
            if phone:
                customer.phone = phone
            customer.save()

        cart = request.session.get('cart') or {}
        products = Products.get_products_by_id(list(cart.keys()))
        for product in products:
            Order(
                customer=customer,
                product=product,
                price=product.price,
                phone=phone,
                quantity=cart.get(str(product.id)),
                **address,
            ).save()

        request.session['cart'] = {}
        return redirect('orders')
