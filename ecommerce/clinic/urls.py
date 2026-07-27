from django.urls import path
from . import views

app_name = "clinic"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    # --- Captura en vivo (reemplaza el Excel) ---
    path("captura/movimiento/", views.movimiento_nuevo, name="movimiento_nuevo"),
    path("captura/empleada/", views.empleada_nueva, name="empleada_nueva"),
    path("captura/gasto/", views.gasto_nuevo, name="gasto_nuevo"),
    path("inventario/", views.inventario, name="inventario"),
]
