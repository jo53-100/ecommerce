from django.shortcuts import render, redirect
from django.contrib.auth.hashers import check_password
from store.models.customers import Customer
from django.views import View
from store.models.products import Products
from store.models.orders import Order

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
        return render(request, 'checkout.html', {'cart_items': cart_items})

    def post(self, request):
        address = request.POST.get('address')
        phone = request.POST.get('phone')
        customer = request.session.get('customer')
        cart = request.session.get('cart', {})
        product_ids = [k.split('_')[0] for k in cart.keys()]
        products = Products.get_products_by_id(product_ids)
        products_dict = {str(p.id): p for p in products}

        for key, qty in cart.items():
            parts = key.split('_')
            prod_id = parts[0]
            color = parts[1] if len(parts) > 1 else None
            product = products_dict.get(prod_id)
            if product:
                order = Order(
                    customer=Customer(id=customer),
                    product=product,
                    price=product.price,
                    address=address,
                    phone=phone,
                    quantity=qty,
                    # Note: You might want to save color in the order model later.
                )
                order.save()
                
        request.session['cart'] = {}

        return redirect('cart')
