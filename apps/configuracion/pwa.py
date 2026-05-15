"""Endpoints PWA: manifest dinámico y service worker mínimo.

El manifest se genera desde la `ConfiguracionGeneral` para que nombre, color e
ícono reflejen siempre lo que el dueño tiene configurado. Si hay logo subido a
Cloudinary se generan los íconos 192/512 con transformaciones; si no, se usa el
SVG genérico de respaldo.

El service worker es mínimo: solo lo necesario para que Chrome/Edge marquen el
sitio como instalable. No cachea nada (offline real queda fuera de scope).
"""
from django.http import HttpResponse, JsonResponse
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt

from .models import ConfiguracionGeneral


CLOUDINARY_UPLOAD_MARKER = '/image/upload/'


def _cloudinary_icon(url, size):
    """Inserta transformación Cloudinary para generar un PNG cuadrado de `size`px
    con padding blanco. Si no es URL de Cloudinary devuelve la URL original."""
    if not url or CLOUDINARY_UPLOAD_MARKER not in url:
        return url
    transform = f'f_png,c_pad,w_{size},h_{size},b_white,q_auto'
    return url.replace(CLOUDINARY_UPLOAD_MARKER, f'{CLOUDINARY_UPLOAD_MARKER}{transform}/', 1)


def _build_icons(request, cfg):
    """Lista de íconos para el manifest. Cuando hay logo en Cloudinary genera
    PNG 192/512 a la medida; si no, usa el SVG estático de respaldo."""
    logo_url = ''
    if cfg and cfg.logo:
        try:
            logo_url = request.build_absolute_uri(cfg.logo.url)
        except Exception:
            logo_url = ''

    if logo_url and CLOUDINARY_UPLOAD_MARKER in logo_url:
        return [
            {'src': _cloudinary_icon(logo_url, 192), 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': _cloudinary_icon(logo_url, 512), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
        ]

    fallback = request.build_absolute_uri(static('icons/app-icon.svg'))
    return [
        {'src': fallback, 'sizes': 'any', 'type': 'image/svg+xml', 'purpose': 'any'},
    ]


def apple_touch_icon_url(request, cfg):
    """URL del apple-touch-icon (PNG 180x180) para iOS. Devuelve cadena vacía si
    no hay logo en Cloudinary — iOS usará su placeholder por defecto."""
    if cfg and cfg.logo:
        try:
            abs_url = request.build_absolute_uri(cfg.logo.url)
        except Exception:
            return ''
        if CLOUDINARY_UPLOAD_MARKER in abs_url:
            return _cloudinary_icon(abs_url, 180)
    return ''


def _short_name(nombre, limit=12):
    """Toma las primeras palabras de `nombre` sin pasar de `limit` caracteres,
    para que aparezca completo bajo el ícono en pantalla de inicio."""
    if not nombre:
        return 'Tienda'
    if len(nombre) <= limit:
        return nombre
    out = ''
    for palabra in nombre.split():
        siguiente = (out + ' ' + palabra).strip()
        if len(siguiente) > limit:
            break
        out = siguiente
    return out or nombre[:limit].strip() or 'Tienda'


@cache_control(max_age=300, public=True)
def manifest(request):
    cfg = ConfiguracionGeneral.objects.first()
    nombre = (cfg.nombre_negocio if cfg else 'Sistema Tienda') or 'Sistema Tienda'
    color = (cfg.color_primario if cfg else '#4F46E5') or '#4F46E5'

    data = {
        'name': nombre,
        'short_name': _short_name(nombre),
        'description': (cfg.slogan if cfg and cfg.slogan else 'Sistema de gestión'),
        'lang': 'es',
        'dir': 'ltr',
        'start_url': '/usuarios/dashboard/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'any',
        'background_color': '#FFFFFF',
        'theme_color': color,
        'icons': _build_icons(request, cfg),
        'categories': ['business', 'productivity'],
    }
    return JsonResponse(
        data,
        json_dumps_params={'ensure_ascii': False},
        content_type='application/manifest+json',
    )


SERVICE_WORKER_JS = """\
// Service worker minimo: solo presencia, sin caching.
// Se actualiza inmediatamente y nunca intercepta requests.
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  // No-op: dejamos que el navegador maneje la peticion normalmente.
});
"""


@csrf_exempt
@cache_control(max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def service_worker(request):
    resp = HttpResponse(SERVICE_WORKER_JS, content_type='application/javascript')
    # Required header para que el SW pueda controlar el root
    resp['Service-Worker-Allowed'] = '/'
    return resp
