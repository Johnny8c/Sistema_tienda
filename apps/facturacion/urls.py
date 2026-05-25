from django.urls import path
from . import views

urlpatterns = [
    path('configuracion/',         views.configuracion_sri,    name='configuracion_sri'),
    path('',                       views.lista_facturas,       name='lista_facturas'),
    path('<int:pk>/',              views.detalle_factura,      name='detalle_factura'),
    path('venta/<int:venta_pk>/emitir/', views.emitir_factura_venta, name='emitir_factura_venta'),
    path('<int:pk>/reemitir/',     views.reemitir_factura,     name='reemitir_factura'),
    path('<int:pk>/verificar/',    views.verificar_autorizacion, name='verificar_autorizacion'),
    path('<int:pk>/xml/',          views.descargar_xml,        name='descargar_xml'),
    path('<int:pk>/ride/',         views.descargar_ride,       name='descargar_ride'),
    path('<int:pk>/email/',        views.reenviar_email_factura, name='reenviar_email_factura'),
]
