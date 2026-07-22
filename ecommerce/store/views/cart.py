from django.shortcuts import render
from django.views import View
from store.models.products import Products
from store.models.customers import Customer


class Cart(View):
    def get(self, request):
        cart = request.session.get('cart', {})
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

        return render(request, 'cart.html', {
            'cart_items': cart_items,
            'customer': customer,
        })
