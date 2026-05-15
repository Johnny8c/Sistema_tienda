from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from apps.configuracion import pwa

urlpatterns = [
    path('admin/', admin.site.urls),
    # PWA — manifest y service worker en la raíz para controlar todo el sitio
    path('manifest.webmanifest', pwa.manifest, name='pwa_manifest'),
    path('sw.js', pwa.service_worker, name='pwa_service_worker'),
    path('', include('apps.usuarios.urls')),
    path('clientes/', include('apps.clientes.urls')),
    path('inventario/', include('apps.inventario.urls')),
    path('ventas/', include('apps.ventas.urls')),
    path('deudores/', include('apps.deudores.urls')),
    path('reportes/', include('apps.reportes.urls')),
    path('proveedores/', include('apps.proveedores.urls')),
    path('sri/', include('apps.facturacion.urls')),
    path('configuracion/', include('apps.configuracion.urls')),
]

if settings.DEBUG and hasattr(settings, 'MEDIA_ROOT'):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
