from django.shortcuts import render, redirect
from django.views import View
from django.utils.translation import gettext as _
from store.models.customers import Customer
from store.models.orders import Order

# Fields the customer may edit from their account screen.
PROFILE_FIELDS = ['first_name', 'last_name', 'phone']
ADDRESS_FIELDS = [
    'recipient_name', 'street_address', 'address_line2',
    'city', 'state', 'zip_code', 'country',
]


class Profile(View):

    def _context(self, customer, **extra):
        orders = Order.get_orders_by_customer(customer.id)
        ctx = {
            'customer': customer,
            'orders': orders,
            'order_count': orders.count(),
        }
        ctx.update(extra)
        return ctx

    def get(self, request):
        customer = Customer.objects.get(id=request.session.get('customer'))
        return render(request, 'profile.html', self._context(customer))

    def post(self, request):
        customer = Customer.objects.get(id=request.session.get('customer'))

        for field in PROFILE_FIELDS + ADDRESS_FIELDS:
            if field in request.POST:
                setattr(customer, field, (request.POST.get(field) or '').strip())

        if not customer.first_name or not customer.last_name:
            return render(request, 'profile.html', self._context(
                customer, error=_('First and last name are required.')))

        customer.save()
        return render(request, 'profile.html', self._context(
            customer, message=_('Your account has been updated.')))
