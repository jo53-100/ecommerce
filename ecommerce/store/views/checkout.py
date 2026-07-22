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
    def get(self, request):
        cart = request.session.get('cart', {})
        if not cart:
            return redirect('cart')
        product_ids = [k.split('_')[0] for k in cart.keys()]
        products = Products.get_products_by_id(product_ids)

        products_dict = {str(p.id): p for p in products}
        cart_items = []
        for key, qty in cart.items():
            parts = key.split('_')
            prod_id = parts[0]
            color = parts[1] if len(parts) > 1 else None
            product = products_dict.get(prod_id)
            if product:
                cart_items.append({
                    'cart_key': key,
                    'product': product,
                    'color': color,
                    'qty': qty,
                    'subtotal': product.price * qty
                })

        customer = None
        customer_id = request.session.get('customer')
        if customer_id:
            customer = Customer.objects.filter(id=customer_id).first()

        return render(request, 'checkout.html', {
            'cart_items': cart_items,
            'customer': customer,
        })

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

        cart = request.session.get('cart', {})
        product_ids = [k.split('_')[0] for k in cart.keys()]
        products = Products.get_products_by_id(product_ids)
        products_dict = {str(p.id): p for p in products}

        for key, qty in cart.items():
            parts = key.split('_')
            prod_id = parts[0]
            product = products_dict.get(prod_id)
            if product:
                Order(
                    customer=customer,
                    product=product,
                    price=product.price,
                    phone=phone,
                    quantity=qty,
                    **address,
                ).save()

        request.session['cart'] = {}
        return redirect('orders')
