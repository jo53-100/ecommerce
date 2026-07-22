from django.shortcuts import render, redirect, HttpResponseRedirect
from store.models.products import Products
from store.models.categories import Category
from django.views import View

class Index(View):

    def post(self, request):
        product = request.POST.get('product')
        remove = request.POST.get('remove')
        remove_all = request.POST.get('remove_all')
        color = request.POST.get('color')
        source = request.POST.get('source')
        
        cart_key = f"{product}_{color}" if color and color != 'undefined' else product

        qty_str = request.POST.get('qty', '1')
        try:
            qty_add = int(qty_str)
        except ValueError:
            qty_add = 1

        buy_now = request.POST.get('buy_now', '0') == '1'

        cart = request.session.get('cart')
        if not cart:
            cart = {}

        if remove_all:
            if cart_key in cart:
                cart.pop(cart_key)
        else:
            quantity = cart.get(cart_key)
            if quantity:
                if remove:
                    if quantity <= 1:
                        cart.pop(cart_key)
                    else:
                        cart[cart_key] = quantity - 1
                else:
                    cart[cart_key] = quantity + qty_add
            else:
                cart[cart_key] = qty_add

        request.session['cart'] = cart
        print('cart', request.session['cart'])
        
        if buy_now:
            return redirect('checkout')
        
        if source == 'cart':
            return redirect('cart')
            
        return redirect('homepage')

    def get(self, request):
        # print()
        return HttpResponseRedirect(f'/store{request.get_full_path()[1:]}')

def store(request):
    cart = request.session.get('cart')
    if not cart:
        request.session['cart'] = {}
    products = None
    categories = Category.get_all_categories()
    categoryID = request.GET.get('category')
    if categoryID:
        products = Products.get_all_products_by_categoryid(categoryID)
    else:
        products = Products.get_all_products()

    data = {}
    data['products'] = products
    data['categories'] = categories

    print('you are : ', request.session.get('email'))
    return render(request, 'index.html', data)
