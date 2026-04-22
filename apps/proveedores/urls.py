from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_proveedores, name='lista_proveedores'),
    path('nuevo/', views.crear_proveedor, name='crear_proveedor'),
    path('<int:pk>/editar/', views.editar_proveedor, name='editar_proveedor'),
    path('compras/', views.lista_compras, name='lista_compras'),
    path('compras/nueva/', views.crear_compra, name='crear_compra'),
    path('compras/<int:pk>/', views.detalle_compra, name='detalle_compra'),
    path('compras/<int:pk>/pagada/', views.marcar_pagada, name='marcar_pagada'),
]
