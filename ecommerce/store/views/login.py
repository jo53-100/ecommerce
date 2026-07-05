from django.shortcuts import render, redirect, HttpResponseRedirect
from django.views import View
from django.utils.http import url_has_allowed_host_and_scheme
from store.models.customers import Customer
from django.contrib.auth.hashers import check_password


def _safe_redirect_url(request, return_url):
    """Only honour return_url when it points back at this site.

    Prevents an open-redirect: without this check an attacker could send a
    victim to /login/?return_url=https://evil.example and bounce them off-site
    after a successful login.
    """
    if return_url and url_has_allowed_host_and_scheme(
        return_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return return_url
    return None


class Login(View):

    def get(self, request):
        return render(request, 'login.html', {
            'return_url': request.GET.get('return_url', ''),
        })

    def post(self, request):
        email = request.POST.get('email')
        password = request.POST.get('password')
        # Carried through the form so it is per-request, not shared class state.
        return_url = request.POST.get('return_url') or request.GET.get('return_url')

        customer = Customer.get_customer_by_email(email)
        if customer and check_password(password, customer.password):
            request.session['customer'] = customer.id
            safe_url = _safe_redirect_url(request, return_url)
            return HttpResponseRedirect(safe_url) if safe_url else redirect('homepage')

        return render(request, 'login.html', {
            'error': 'Invalido !!',
            'return_url': return_url or '',
        })


def logout(request):
    request.session.clear()
    return redirect('login')
