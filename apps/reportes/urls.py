from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_reportes, name='reportes'),
    path('cartera/', views.antiguedad_cartera, name='reporte_cartera'),
    path('adelantos-por-vencer/', views.adelantos_por_vencer, name='reporte_adelantos'),
    path('top-deudores/', views.top_deudores, name='reporte_top_deudores'),
    path('cierre-caja/', views.cierre_caja, name='cierre_caja'),
    path('historial-inventario/', views.historial_inventario, name='historial_inventario'),
]
