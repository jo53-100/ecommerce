"""
Reportes derivados. Nada de esto se captura a mano: todo sale de Transaction.
Esto es lo que antes vivia repartido entre 40 hojas de Excel.
"""
from django.db.models import Sum, Count
from .models import Transaction, Expense, Employee


def favorite_services(year, month=None, limit=10):
    """Servicio favorito / ranking por ingreso."""
    qs = Transaction.objects.filter(kind="service", date__year=year)
    if month:
        qs = qs.filter(date__month=month)
    return (qs.values("service_type__name")
              .annotate(ingreso=Sum("amount"), veces=Count("id"))
              .order_by("-ingreso"))


def payroll(employee, year, month):
    """Nomina de una empleada en un mes: base + comision derivada."""
    txs = Transaction.objects.filter(employee=employee, kind="service",
                                     date__year=year, date__month=month)
    sales = txs.aggregate(s=Sum("amount"))["s"] or 0
    commission = sales * employee.commission_rate
    base_month = employee.base_salary_weekly * 4
    return {"empleada": employee.name, "ventas_servicio": sales,
            "comision": commission, "base_mensual": base_month,
            "total": base_month + commission}


def monthly_pnl(year, month):
    """Estado de resultados del mes (reemplaza la seccion GLOBAL del Excel)."""
    f = dict(date__year=year, date__month=month)
    income = Transaction.objects.filter(kind__in=["service", "product_sale"], **f).aggregate(s=Sum("amount"))["s"] or 0
    expenses = Expense.objects.filter(**f).aggregate(s=Sum("amount"))["s"] or 0
    return {"ingresos": income, "gastos": expenses, "utilidad": income - expenses}
