from django.urls import path
from .views.home import Index, store
from .views.signup import Signup
from .views.login import Login, logout
from .views.cart import Cart
from .views.checkout import CheckOut
from .views.orders import OrderView
from .views.profile import Profile
from .views.payments import checkout_success, checkout_cancel, stripe_webhook
from .middlewares.auth import auth_middleware

urlpatterns = [
    path('', Index.as_view(), name='homepage'),
    path('store/', store, name='store'),
    path('signup/', Signup.as_view(), name='signup'),
    path('login/', Login.as_view(), name='login'),
    path('logout/', logout, name='logout'),
    path('cart/', auth_middleware(Cart.as_view()), name='cart'),
    path('check-out/', auth_middleware(CheckOut.as_view()), name='checkout'),
    path('orders/', auth_middleware(OrderView.as_view()), name='orders'),
    path('account/', auth_middleware(Profile.as_view()), name='profile'),

    # --- Stripe ---
    # Shoppers return here from the hosted Stripe page.
    path('checkout/success/', auth_middleware(checkout_success),
         name='checkout_success'),
    path('checkout/cancel/', auth_middleware(checkout_cancel),
         name='checkout_cancel'),
    # Called by Stripe, not by a browser — must stay unauthenticated.
    path('stripe/webhook/', stripe_webhook, name='stripe_webhook'),
    # Same view without the trailing slash. APPEND_SLASH cannot redirect a POST
    # without dropping the body, so it raises a 500 instead — which would mean
    # an endpoint URL configured without the slash silently never fulfils an
    # order. Accept both spellings rather than depend on getting it right.
    path('stripe/webhook', stripe_webhook),
]
