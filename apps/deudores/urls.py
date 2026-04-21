from django.urls import path
from . import views

urlpatterns = [
    # Adelantos
    path('adelantos/', views.lista_adelantos, name='lista_adelantos'),
    path('adelantos/nuevo/', views.crear_adelanto_view, name='crear_adelanto'),
    path('adelantos/<int:pk>/', views.detalle_adelanto, name='detalle_adelanto'),
    path('adelantos/<int:pk>/abonar/', views.abonar_adelanto, name='abonar_adelanto'),
    path('adelantos/<int:pk>/completar/', views.completar_adelanto_view, name='completar_adelanto'),
    path('adelantos/<int:pk>/cancelar/', views.cancelar_adelanto_view, name='cancelar_adelanto'),

    # Deudas
    path('deudas/', views.lista_deudas, name='lista_deudas'),
    path('deudas/<int:pk>/', views.detalle_deuda, name='detalle_deuda'),
    path('deudas/<int:pk>/abonar/', views.abonar_deuda, name='abonar_deuda'),
    path('deudas/<int:pk>/saldar/', views.saldar_deuda_view, name='saldar_deuda'),
    path('deudas/<int:pk>/condonar/', views.condonar_deuda_view, name='condonar_deuda'),

    # POS
    path('pos/', views.pos, name='pos'),
    path('pos/procesar/', views.procesar_venta, name='procesar_venta'),
]
