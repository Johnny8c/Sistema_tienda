from django.urls import path
from . import views

urlpatterns = [
    path('',                 views.panel,           name='config_panel'),
    path('datos-negocio/',   views.datos_negocio,   name='config_datos_negocio'),
    path('preferencias/',    views.preferencias,    name='config_preferencias'),
    path('mi-cuenta/',       views.mi_cuenta,       name='config_mi_cuenta'),
]
