"""
Formularios de captura en vivo.

Estos formularios son el reemplazo del Excel: la duena / recepcion captura
aqui cada movimiento del dia. La nomina y los reportes NO se capturan, se
derivan de estos movimientos (ver models.Transaction y reports.py).
"""
import datetime as dt
from django import forms
from django.db.models import F
from .models import Transaction, Product, Employee, Expense


_DATE_WIDGET = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")

# Tipos de movimiento que salen del inventario (descuentan stock y su monto
# se deriva del precio del producto por la cantidad).
_PRODUCT_KINDS = ("product_sale", "product_use")


class TransactionForm(forms.ModelForm):
    """Un movimiento: servicio realizado, venta o uso de producto, propina.

    Si es servicio y se indica la empleada, alimenta su comision/nomina.
    Si es venta/uso de producto, descuenta `cantidad` del inventario y el
    monto se calcula como (precio del producto x cantidad).
    """
    cantidad = forms.IntegerField(
        label="Cantidad (para inventario)", min_value=1, initial=1, required=False,
        help_text="Solo para venta/uso de producto: cuantas piezas salen del stock.",
    )

    class Meta:
        model = Transaction
        fields = [
            "date", "kind", "employee", "service_type", "product",
            "client", "amount", "payment_method", "walk_in", "cantidad", "note",
        ]
        widgets = {"date": _DATE_WIDGET}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["date"].initial = dt.date.today()
        # En captura en vivo solo se ofrecen catalogos activos.
        self.fields["service_type"].queryset = self.fields["service_type"].queryset.filter(active=True)
        self.fields["employee"].queryset = self.fields["employee"].queryset.filter(active=True)
        # En ventas/usos de producto el monto se puede dejar vacio: se calcula
        # solo como precio x cantidad. En servicios/propinas sigue siendo obligatorio.
        self.fields["amount"].required = False
        self.fields["amount"].help_text = (
            "Venta/uso de producto: dejalo vacio y se calcula como precio x "
            "cantidad (o captura un monto para forzar un precio distinto). "
            "Servicio o propina: captura el monto cobrado."
        )

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind")
        product = cleaned.get("product")
        qty = cleaned.get("cantidad") or 1
        amount = cleaned.get("amount")

        if kind in _PRODUCT_KINDS:
            if not product:
                self.add_error("product", "Selecciona el producto que sale del inventario.")
            elif amount is None:
                # Precio de referencia: venta -> precio de venta; uso -> costo.
                unit = product.sale_price if kind == "product_sale" else product.unit_cost
                cleaned["amount"] = unit * qty
        elif amount is None:
            # Servicios y propinas: el monto es obligatorio, no hay como derivarlo.
            self.add_error("amount", "Captura el monto cobrado.")

        return cleaned

    def save(self, commit=True):
        tx = super().save(commit=commit)
        # Descontar inventario en ventas / usos de producto.
        # F() evita condiciones de carrera sobre el stock.
        if commit and tx.product_id and tx.kind in ("product_sale", "product_use"):
            qty = self.cleaned_data.get("cantidad") or 1
            Product.objects.filter(pk=tx.product_id).update(stock=F("stock") - qty)
        return tx


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "for_sale", "unit_cost", "sale_price", "stock"]
        labels = {"stock": "Existencia inicial"}


class RestockForm(forms.Form):
    """Sumar piezas al stock de un producto existente (entrada de inventario)."""
    product = forms.ModelChoiceField(
        label="Producto", queryset=Product.objects.all().order_by("name"))
    units = forms.IntegerField(label="Piezas a agregar", min_value=1)

    def save(self):
        p = self.cleaned_data["product"]
        Product.objects.filter(pk=p.pk).update(stock=F("stock") + self.cleaned_data["units"])
        return p


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ["name", "role", "base_salary_weekly", "commission_rate", "active"]


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["date", "category", "amount", "note"]
        widgets = {"date": _DATE_WIDGET}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.fields["date"].initial = dt.date.today()
