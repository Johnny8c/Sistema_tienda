from django.urls import path
from . import views

urlpatterns = [
    path('',               views.lista_ventas, name='lista_ventas'),
    path('<int:pk>/nota/', views.nota_venta,   name='nota_venta'),
]
