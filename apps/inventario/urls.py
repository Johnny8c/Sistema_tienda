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
    # Etiquetas pegables (impresión por lotes)
    path('etiquetas/',                    views.imprimir_etiquetas,             name='imprimir_etiquetas'),
    path('etiquetas/api/marcar/',          views.api_etiquetas_marcar_impresas,       name='api_etiquetas_marcar'),
    path('etiquetas/api/reiniciar/',       views.api_etiquetas_reiniciar_impresas,    name='api_etiquetas_reiniciar'),
    path('etiquetas/api/importar/',        views.api_etiquetas_importar_localstorage, name='api_etiquetas_importar'),
    path('etiquetas/api/marcar-pendiente/',views.api_etiquetas_marcar_pendiente,      name='api_etiquetas_marcar_pendiente'),
    # Categorías
    path('categorias/',                     views.lista_categorias,    name='lista_categorias'),
    path('categorias/nueva/',               views.crear_categoria,     name='crear_categoria'),
    path('categorias/<int:pk>/editar/',     views.editar_categoria,    name='editar_categoria'),
    path('categorias/<int:pk>/toggle/',     views.toggle_categoria,    name='toggle_categoria'),
    path('categorias/<int:pk>/eliminar/',   views.eliminar_categoria,  name='eliminar_categoria'),
]
