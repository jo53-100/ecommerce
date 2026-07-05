from django.db import models


class AddressMixin(models.Model):
    """Reusable set of classic postal-address fields.

    Shared by Customer (the shopper's saved shipping address) and Order (a
    snapshot of where a particular order was shipped, kept even if the customer
    later edits their saved address).
    """
    recipient_name = models.CharField("Recipient", max_length=100, blank=True, default='')
    street_address = models.CharField("Street address", max_length=120, blank=True, default='')
    address_line2 = models.CharField("Apt / suite / unit", max_length=120, blank=True, default='')
    city = models.CharField(max_length=60, blank=True, default='')
    state = models.CharField("State / province", max_length=60, blank=True, default='')
    zip_code = models.CharField("ZIP / postal code", max_length=12, blank=True, default='')
    country = models.CharField(max_length=60, blank=True, default='United States')

    class Meta:
        abstract = True

    @property
    def has_address(self):
        return bool(self.street_address and self.city)

    @property
    def city_line(self):
        """'City, ST 12345' — the middle line of a postal address."""
        bits = self.city
        if self.state:
            bits = f"{bits}, {self.state}" if bits else self.state
        if self.zip_code:
            bits = f"{bits} {self.zip_code}" if bits else self.zip_code
        return bits

    @property
    def full_address(self):
        """Multi-line human-readable address (blank lines removed)."""
        lines = [self.recipient_name, self.street_address, self.address_line2,
                 self.city_line, self.country]
        return "\n".join(line for line in lines if line and line.strip())
