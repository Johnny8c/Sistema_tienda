from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_clientes, name='lista_clientes'),
    path('nuevo/', views.crear_cliente, name='crear_cliente'),
    path('<int:pk>/editar/', views.editar_cliente, name='editar_cliente'),
    path('<int:pk>/', views.detalle_cliente, name='detalle_cliente'),
    path('api/crear/', views.api_crear_cliente, name='api_crear_cliente'),
]
