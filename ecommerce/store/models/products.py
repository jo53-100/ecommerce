from decimal import Decimal

from django.db import models

from .categories import Category


class Products(models.Model):
    """The single source of truth for the catalogue and for stock on hand.

    Money is stored as Decimal, not float or int: two decimal places is exactly
    what pesos-and-centavos needs, and Decimal arithmetic does not accumulate
    the rounding error that floats do. Conversion to Stripe's integer minor
    units happens once, at the API boundary (see store.payments).
    """

    name = models.CharField(max_length=60)
    price = models.DecimalField(max_digits=10, decimal_places=2,
                                default=Decimal('0.00'))
    # What the item cost us. Only used for margin reporting; never charged.
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2,
                                    default=Decimal('0.00'))
    category = models.ForeignKey(Category, on_delete=models.CASCADE, default=1)
    description = models.CharField(
        max_length=250, default='', blank=True, null=True)
    image = models.ImageField(upload_to='uploads/products/')

    # --- Inventory ---
    stock = models.PositiveIntegerField(
        default=0, help_text='Units on hand. Decremented when payment clears.')
    # Lets an item be sold without stock control (made to order, services).
    # Existing rows are grandfathered to False by the migration so that adding
    # this field cannot silently make the whole catalogue unbuyable.
    track_inventory = models.BooleanField(
        default=True,
        help_text='Uncheck to sell this item without stock limits.')
    # False = internal supply. Kept out of the storefront but still stocked and
    # reportable, which is what the back office calls an "insumo".
    for_sale = models.BooleanField(
        default=True, help_text='Show this item in the storefront.')

    class Meta:
        verbose_name_plural = 'Products'

    def __str__(self):
        return self.name

    @property
    def price_units(self):
        """Whole pesos, for the storefront's large-figure price display."""
        return int(self.price)

    @property
    def price_cents(self):
        """Centavos as a zero-padded two-character string ('00', '50')."""
        return f'{int((self.price - int(self.price)) * 100):02d}'

    @property
    def in_stock(self):
        return not self.track_inventory or self.stock > 0

    def can_supply(self, qty):
        """Is there enough on hand to fulfil `qty` units?"""
        return not self.track_inventory or self.stock >= qty

    @staticmethod
    def get_products_by_id(ids):
        return Products.objects.filter(id__in=ids)

    @staticmethod
    def get_all_products():
        # Storefront listings only ever show sellable items; internal supplies
        # live in the same table but never reach a shopper.
        return Products.objects.filter(for_sale=True)

    @staticmethod
    def get_all_products_by_categoryid(category_id):
        if category_id:
            return Products.objects.filter(category=category_id, for_sale=True)
        else:
            return Products.get_all_products()
