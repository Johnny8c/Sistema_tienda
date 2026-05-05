from django.urls import path
from . import views

urlpatterns = [
    # Catálogo
    path('',                            views.lista_inventario,   name='lista_inventario'),
    path('nuevo/',                      views.crear_producto,     name='crear_producto'),
    path('<int:pk>/',                   views.detalle_producto,   name='detalle_producto'),
    path('<int:pk>/editar/',            views.editar_producto,    name='editar_producto'),
    path('<int:pk>/desactivar/',        views.desactivar_producto, name='desactivar_producto'),
    # Variantes
    path('<int:catalogo_pk>/variante/nueva/',     views.agregar_variante,   name='agregar_variante'),
    path('variante/<int:pk>/editar/',             views.editar_variante,    name='editar_variante'),
    path('variante/<int:pk>/stock/',              views.ajustar_stock,      name='ajustar_stock'),
    path('variante/<int:pk>/desactivar/',         views.desactivar_variante, name='desactivar_variante'),
    # Consultar precio / API
    path('consultar/',    views.consultar_precio, name='consultar_precio'),
    path('api/codigo/',   views.api_buscar_codigo, name='api_buscar_codigo'),
]
