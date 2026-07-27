"""Dashboard interno (solo personal). Reemplaza la vista tabular del admin."""
import datetime as dt
from decimal import Decimal
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count
from django.shortcuts import redirect, render
from .models import Transaction, Expense, Employee, Product, ServiceType
from .forms import (TransactionForm, ProductForm, RestockForm,
                    EmployeeForm, ExpenseForm)

YEAR = 2026
MES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
       "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
MES_ABBR = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
            "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
INCOME_KINDS = ["service", "product_sale"]


def _money(qs):
    return qs.aggregate(s=Sum("amount"))["s"] or Decimal(0)


@staff_member_required
def dashboard(request):
    try:
        month = int(request.GET.get("month", 0)) or None
    except ValueError:
        month = None

    scope = dict(date__year=YEAR)
    if month:
        scope["date__month"] = month

    # --- KPIs del periodo seleccionado ---
    income = _money(Transaction.objects.filter(kind__in=INCOME_KINDS, **scope))
    expenses = _money(Expense.objects.filter(**scope))
    profit = income - expenses
    n_services = Transaction.objects.filter(kind="service", **scope).count()

    # --- Serie mensual (siempre el ano completo, para la grafica) ---
    months, m_income, m_expense, m_profit = [], [], [], []
    for m in range(1, 13):
        inc = _money(Transaction.objects.filter(kind__in=INCOME_KINDS, date__year=YEAR, date__month=m))
        exp = _money(Expense.objects.filter(date__year=YEAR, date__month=m))
        months.append(MES_ABBR[m])
        m_income.append(float(inc))
        m_expense.append(float(exp))
        m_profit.append(float(inc - exp))

    # --- Top servicios del periodo ---
    top = (Transaction.objects.filter(kind="service", **scope)
           .values("service_type__name")
           .annotate(total=Sum("amount"))
           .order_by("-total")[:8])
    top_labels = [r["service_type__name"] or "(sin nombre)" for r in top]
    top_values = [float(r["total"]) for r in top]

    # --- Ingreso por categoria (servicios) + productos ---
    cat_rows = (Transaction.objects.filter(kind="service", **scope)
                .values("service_type__category")
                .annotate(total=Sum("amount")).order_by("-total"))
    cat_map = dict(ServiceType.CATEGORY_CHOICES)
    cat_labels = [cat_map.get(r["service_type__category"], "Otro") for r in cat_rows]
    cat_values = [float(r["total"]) for r in cat_rows]
    prod_total = _money(Transaction.objects.filter(kind="product_sale", **scope))
    if prod_total:
        cat_labels.append("Productos")
        cat_values.append(float(prod_total))

    # --- Inventario / productos (con venta del periodo) ---
    products = []
    for p in Product.objects.all().order_by("name"):
        sold = _money(Transaction.objects.filter(kind="product_sale", product=p, **scope))
        products.append({
            "name": p.name, "for_sale": p.for_sale, "stock": p.stock,
            "low": p.stock <= 0, "sold": float(sold),
        })
    products.sort(key=lambda x: x["sold"], reverse=True)

    # --- Nomina por empleada (periodo) ---
    payroll = []
    weeks = 4 if month else 52
    for e in Employee.objects.filter(active=True):
        sales = _money(Transaction.objects.filter(employee=e, kind="service", **scope))
        commission = sales * e.commission_rate
        base = e.base_salary_weekly * weeks
        payroll.append({
            "name": e.name, "role": e.get_role_display(),
            "sales": float(sales), "commission": float(commission),
            "base": float(base), "total": float(base + commission),
        })

    period_label = f"{MES[month]} {YEAR}" if month else f"Ano {YEAR}"

    ctx = {
        "year": YEAR, "month": month, "period_label": period_label,
        "month_choices": [(i, MES[i]) for i in range(1, 13)],
        "kpi": {"income": income, "expenses": expenses, "profit": profit, "services": n_services},
        "months": months, "m_income": m_income, "m_expense": m_expense, "m_profit": m_profit,
        "top_labels": top_labels, "top_values": top_values,
        "cat_labels": cat_labels, "cat_values": cat_values,
        "products": products, "payroll": payroll,
        "has_stock_data": any(p["stock"] for p in products),
    }
    return render(request, "clinic/dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Captura en vivo: reemplazo del Excel. Todo se guarda como Transaction /
# Product / Employee / Expense; la nomina y los reportes se derivan solos.
# ---------------------------------------------------------------------------

def _save_form(request, form, success_msg, redirect_to="clinic:dashboard"):
    """Patron comun: si POST valido guarda, avisa y redirige; si no, retorna None."""
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, success_msg)
        return redirect(redirect_to)
    return None


@staff_member_required
def movimiento_nuevo(request):
    form = TransactionForm(request.POST or None)
    done = _save_form(request, form, "Movimiento registrado.")
    if done:
        return done
    return render(request, "clinic/form.html", {
        "title": "Registrar movimiento",
        "subtitle": "Servicio, venta/uso de producto o propina del dia.",
        "form": form,
    })


@staff_member_required
def empleada_nueva(request):
    form = EmployeeForm(request.POST or None)
    done = _save_form(request, form, "Empleada guardada.")
    if done:
        return done
    return render(request, "clinic/form.html", {
        "title": "Nueva empleada",
        "subtitle": "El sueldo base y la comision alimentan la nomina derivada.",
        "form": form,
    })


@staff_member_required
def gasto_nuevo(request):
    form = ExpenseForm(request.POST or None)
    done = _save_form(request, form, "Gasto registrado.")
    if done:
        return done
    return render(request, "clinic/form.html", {
        "title": "Registrar gasto",
        "subtitle": "Renta, salarios, servicios, SAT, compras, etc.",
        "form": form,
    })


@staff_member_required
def inventario(request):
    """Una pagina para el inventario: alta de producto, entrada de stock y listado."""
    action = request.POST.get("action")
    product_form = ProductForm(request.POST if action == "new" else None)
    restock_form = RestockForm(request.POST if action == "restock" else None)

    if request.method == "POST":
        if action == "new" and product_form.is_valid():
            product_form.save()
            messages.success(request, "Producto agregado al inventario.")
            return redirect("clinic:inventario")
        if action == "restock" and restock_form.is_valid():
            p = restock_form.save()
            messages.success(request, f"Stock actualizado: {p.name}.")
            return redirect("clinic:inventario")

    products = Product.objects.all().order_by("name")
    return render(request, "clinic/inventario.html", {
        "title": "Inventario",
        "product_form": product_form,
        "restock_form": restock_form,
        "products": products,
    })
