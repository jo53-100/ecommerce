"""
Lovefoot — modelo de datos.

Idea central: TODO el dinero entra como una sola fila en `Transaction`
(un servicio realizado, un producto vendido, un insumo usado, una propina).
La nomina, el inventario, los reportes y las comisiones NO se capturan
aparte: se CALCULAN a partir de estas filas. Eso elimina la doble captura
que hoy existe entre NOMINA_2026.xlsx y BASE_DE_DATOS_2026.xlsx.
"""
from decimal import Decimal
from django.db import models


class Employee(models.Model):
    ROLE_CHOICES = [
        ("podologa", "Podologa"),
        ("cosmetologa", "Cosmetologa"),
        ("masajista", "Masajista"),
        ("admin", "Administracion"),
    ]
    name = models.CharField("Nombre", max_length=100)
    role = models.CharField("Puesto", max_length=20, choices=ROLE_CHOICES, default="podologa")
    base_salary_weekly = models.DecimalField("Sueldo base semanal", max_digits=10, decimal_places=2, default=0)
    # Comision observada en NOMINA: 10% del servicio sin IVA -> 0.10 / 1.16 = 0.0862.
    # Las tasas reales pueden variar por empleada y por servicio/producto: confirmar con la duena.
    commission_rate = models.DecimalField(
        "Tasa de comision", max_digits=6, decimal_places=4, default=0,
        help_text="Fraccion del servicio que se paga como comision (ej. 0.0862)",
    )
    active = models.BooleanField("Activa", default=True)

    class Meta:
        verbose_name = "Empleada"
        verbose_name_plural = "Empleadas"

    def __str__(self):
        return self.name


class ServiceType(models.Model):
    CATEGORY_CHOICES = [
        ("podologia", "Podologia"),
        ("facial", "Facial / Cosmetologia"),
        ("masaje", "Masaje"),
        ("otro", "Otro"),
    ]
    name = models.CharField("Servicio", max_length=120, unique=True)
    category = models.CharField("Categoria", max_length=20, choices=CATEGORY_CHOICES, default="otro")
    price = models.DecimalField("Precio de lista", max_digits=10, decimal_places=2, default=0)
    active = models.BooleanField("Activo", default=True)

    class Meta:
        verbose_name = "Tipo de servicio"
        verbose_name_plural = "Tipos de servicio"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField("Producto", max_length=120, unique=True)
    # Requisito explicito de la duena: diferenciar vendido vs. usado.
    for_sale = models.BooleanField(
        "Es para venta", default=True,
        help_text="Si = se vende al cliente. No = insumo de uso interno.",
    )
    unit_cost = models.DecimalField("Costo unitario", max_digits=10, decimal_places=2, default=0)
    sale_price = models.DecimalField("Precio de venta", max_digits=10, decimal_places=2, default=0)
    stock = models.IntegerField("Existencia", default=0)

    class Meta:
        verbose_name = "Producto / Insumo"
        verbose_name_plural = "Productos / Insumos"

    def __str__(self):
        return self.name


class Client(models.Model):
    name = models.CharField("Nombre", max_length=120)
    age = models.PositiveIntegerField("Edad", null=True, blank=True)
    occupation = models.CharField("Ocupacion", max_length=120, blank=True)
    phone = models.CharField("Celular", max_length=30, blank=True)
    diabetic = models.BooleanField("Diabetes", default=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cliente / Paciente"
        verbose_name_plural = "Clientes / Pacientes"

    def __str__(self):
        return self.name


class Transaction(models.Model):
    """Tabla central de hechos: una fila por movimiento de dinero."""
    KIND_CHOICES = [
        ("service", "Servicio"),
        ("product_sale", "Venta de producto"),
        ("product_use", "Uso de insumo"),
        ("tip", "Propina"),
    ]
    PAYMENT_CHOICES = [
        ("cash", "Efectivo"),
        ("card", "Tarjeta"),
        ("transfer", "Transferencia"),
        ("na", "N/A"),
    ]
    date = models.DateField("Fecha")
    kind = models.CharField("Tipo", max_length=15, choices=KIND_CHOICES)
    employee = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions", verbose_name="Atendio")
    service_type = models.ForeignKey(ServiceType, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Servicio")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Producto")
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Cliente")
    amount = models.DecimalField("Monto", max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField("Pago", max_length=10, choices=PAYMENT_CHOICES, default="na")
    walk_in = models.BooleanField("Sin cita", default=False, help_text="El cliente llego sin cita previa.")
    # Las filas historicas del Excel son agregados diarios (varios clientes en una cifra),
    # no ventas individuales. Esta bandera las distingue de la captura nueva en vivo.
    is_imported_aggregate = models.BooleanField("Importado del Excel", default=False)
    note = models.CharField("Nota", max_length=255, blank=True)

    class Meta:
        verbose_name = "Movimiento"
        verbose_name_plural = "Movimientos"
        indexes = [models.Index(fields=["date", "kind"])]

    @property
    def commission(self):
        """Comision derivada -- no se almacena, se calcula."""
        if self.kind == "service" and self.employee:
            return (self.amount or Decimal(0)) * self.employee.commission_rate
        return Decimal(0)

    def __str__(self):
        label = self.service_type or self.product or self.get_kind_display()
        return f"{self.date} - {label} - ${self.amount}"


class Expense(models.Model):
    CATEGORY_CHOICES = [
        ("rent", "Renta"),
        ("salary", "Salarios"),
        ("utilities", "Servicios (luz, agua, internet)"),
        ("tax", "SAT / Contador"),
        ("supplies", "Compras / Insumos"),
        ("other", "Otro"),
    ]
    date = models.DateField("Fecha")
    category = models.CharField("Categoria", max_length=15, choices=CATEGORY_CHOICES)
    amount = models.DecimalField("Monto", max_digits=10, decimal_places=2)
    note = models.CharField("Nota", max_length=255, blank=True)

    class Meta:
        verbose_name = "Gasto"
        verbose_name_plural = "Gastos"

    def __str__(self):
        return f"{self.date} - {self.get_category_display()} - ${self.amount}"
