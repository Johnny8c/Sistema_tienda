from django.urls import path
from . import views

urlpatterns = [
    path('<int:pk>/nota/', views.nota_venta, name='nota_venta'),
]
