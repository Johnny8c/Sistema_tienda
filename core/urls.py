from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.usuarios.urls')),
    path('clientes/', include('apps.clientes.urls')),
    path('inventario/', include('apps.inventario.urls')),
    path('ventas/', include('apps.ventas.urls')),
    path('deudores/', include('apps.deudores.urls')),
    path('reportes/', include('apps.reportes.urls')),
    path('proveedores/', include('apps.proveedores.urls')),
    path('ventas/', include('apps.ventas.urls')),
]
