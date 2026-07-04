from django.shortcuts import render
from django.views import View
from store.models.products import Products


class Cart(View):
    def get(self, request):
        ids = list(request.session.get('cart').keys())
        products = Products.get_products_by_id(ids)
        print(products)
        return render(request, 'cart.html', {'products': products})
