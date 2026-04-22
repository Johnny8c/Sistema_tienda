from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_inventario, name='lista_inventario'),
    path('nuevo/', views.crear_producto, name='crear_producto'),
    path('consultar/', views.consultar_precio, name='consultar_precio'),
    path('api/codigo/', views.api_buscar_codigo, name='api_buscar_codigo'),
    path('<int:pk>/editar/', views.editar_producto, name='editar_producto'),
    path('<int:pk>/stock/', views.ajustar_stock, name='ajustar_stock'),
    path('<int:pk>/desactivar/', views.desactivar_producto, name='desactivar_producto'),
]
