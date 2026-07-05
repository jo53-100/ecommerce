from django.shortcuts import render
from django.views import View
from store.models.products import Products
from store.models.customers import Customer


class Cart(View):
    def get(self, request):
        ids = list(request.session.get('cart').keys())
        products = Products.get_products_by_id(ids)
        customer = None
        customer_id = request.session.get('customer')
        if customer_id:
            customer = Customer.objects.filter(id=customer_id).first()
        return render(request, 'cart.html', {
            'products': products,
            'customer': customer,
        })
