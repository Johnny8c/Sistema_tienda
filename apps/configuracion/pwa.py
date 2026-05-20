"""Endpoints PWA: manifest dinamico y service worker con cache offline.

El manifest se genera desde la `ConfiguracionGeneral` para que nombre, color e
icono reflejen siempre lo que el dueno tiene configurado. Si hay logo subido a
Cloudinary se generan los iconos 192/512 con transformaciones; si no, se usa el
SVG generico de respaldo.

El service worker:
- Precachea best-effort el catalogo de emergencia y los assets staticos.
- Sirve navegaciones con network-first (cache como fallback si esta offline).
- Sirve assets staticos con cache-first.
- Tiene una pagina de fallback minima cuando se cae todo y no hay cache.
"""
import cloudinary
from django.http import HttpResponse, JsonResponse
from django.templatetags.static import static
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.csrf import csrf_exempt

from .models import ConfiguracionGeneral


CLOUDINARY_UPLOAD_MARKER = '/image/upload/'

# Bump esta version cada vez que se cambia el JS del service worker, para
# forzar a los navegadores a descargar la nueva version y limpiar caches viejos.
SW_CACHE_VERSION = 'v3-2026-05-20'

# Path en Cloudinary donde generar_emergencia sube el catalogo HTML.
EMERGENCIA_PUBLIC_ID = 'emergencia/catalogo.html'


def _cloudinary_icon(url, size):
    """Inserta transformacion Cloudinary para generar un PNG cuadrado de `size`px
    con marco blanco alrededor del logo (logo ocupa 80%, resto blanco).
    Si no es URL de Cloudinary devuelve la URL original."""
    if not url or CLOUDINARY_UPLOAD_MARKER not in url:
        return url
    inner = int(size * 0.8)
    transform = (
        f'c_fit,w_{inner},h_{inner}/'
        f'c_pad,w_{size},h_{size},b_white,f_png,q_auto'
    )
    return url.replace(CLOUDINARY_UPLOAD_MARKER, f'{CLOUDINARY_UPLOAD_MARKER}{transform}/', 1)


def _build_icons(request, cfg):
    """Lista de iconos para el manifest. Cuando hay logo en Cloudinary genera
    PNG 192/512 a la medida; si no, usa el SVG estatico de respaldo."""
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
    """URL del apple-touch-icon (PNG 180x180) para iOS. Devuelve cadena vacia si
    no hay logo en Cloudinary - iOS usara su placeholder por defecto."""
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
    para que aparezca completo bajo el icono en pantalla de inicio."""
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
        'description': (cfg.slogan if cfg and cfg.slogan else 'Sistema de gestion'),
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


def _emergencia_url():
    """URL publica del catalogo HTML de emergencia en Cloudinary, o cadena
    vacia si no hay cloudinary configurado."""
    cloud_name = cloudinary.config().cloud_name
    if not cloud_name:
        return ''
    return f'https://res.cloudinary.com/{cloud_name}/raw/upload/{EMERGENCIA_PUBLIC_ID}'


# Template del Service Worker. Se rellena con valores dinamicos en service_worker().
SERVICE_WORKER_JS_TEMPLATE = r"""// Auto-generado por apps/configuracion/pwa.py
// Bump SW_CACHE_VERSION en pwa.py cuando se modifique este archivo.

const VERSION = '%%CACHE_VERSION%%';
const SHELL_CACHE = 'sistema-shell-' + VERSION;
const PAGES_CACHE = 'sistema-pages-' + VERSION;
const EXTERNAL_CACHE = 'sistema-ext-' + VERSION;

// URL publica del catalogo de emergencia (Cloudinary). Puede estar vacio si
// aun no esta configurado; en ese caso el SW funciona igual sin el fallback.
const EMERGENCIA_URL = '%%EMERGENCIA_URL%%';

// Assets propios del app shell que se precachean al instalar el SW. Son los
// archivos que cambian poco; si fallan al precache (404) no se cae la
// instalacion del SW (uno por uno con try/catch).
const SHELL_ASSETS = %%SHELL_ASSETS%%;

// Pagina HTML minima que se devuelve cuando el navegador navega y NO hay red
// NI cache. Incluye link directo al catalogo de emergencia si existe.
const OFFLINE_FALLBACK_HTML = `<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sin conexion</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;background:#F3F4F6;color:#111827;
  margin:0;padding:32px 20px;text-align:center;line-height:1.5}
.card{max-width:380px;margin:40px auto;background:#fff;border-radius:14px;padding:28px 24px;
  box-shadow:0 4px 12px rgba(0,0,0,.08)}
h1{font-size:20px;margin:0 0 8px;color:#DC2626}
p{font-size:14px;color:#4B5563;margin:6px 0}
a.btn{display:inline-block;margin-top:18px;padding:12px 24px;background:#4F46E5;
  color:#fff;border-radius:10px;text-decoration:none;font-weight:700;font-size:14px}
small{color:#9CA3AF;font-size:12px;display:block;margin-top:16px}
.icon{font-size:48px;margin-bottom:8px}
</style></head><body>
<div class="card">
<div class="icon">📡</div>
<h1>Sin conexion</h1>
<p>El sistema no esta disponible en este momento.</p>
<p>Podes consultar precios y stock en el catalogo de emergencia:</p>
${EMERGENCIA_URL ? `<a class="btn" href="${EMERGENCIA_URL}">Abrir catalogo</a>` : '<p><b>Catalogo no disponible aun.</b></p>'}
<small>Cuando vuelva la conexion, recarga esta pagina.</small>
</div></body></html>`;

// ─── INSTALL ────────────────────────────────────────────────────────────────
// Precachear best-effort. Si algun asset 404, no falla la instalacion del SW.
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then(async (cache) => {
      await Promise.all(SHELL_ASSETS.map(async (url) => {
        try {
          const resp = await fetch(url, { credentials: 'same-origin' });
          if (resp.ok) await cache.put(url, resp);
        } catch (e) { /* ignore individual failures */ }
      }));
      // Emergencia URL: cross-origin, mejor con mode 'no-cors' para opacar respuesta
      if (EMERGENCIA_URL) {
        try {
          const resp = await fetch(EMERGENCIA_URL, { mode: 'cors' });
          if (resp.ok) {
            const extCache = await caches.open(EXTERNAL_CACHE);
            await extCache.put(EMERGENCIA_URL, resp.clone());
          }
        } catch (e) { /* sin internet en el install, se intentara al primer fetch */ }
      }
      await self.skipWaiting();
    })
  );
});

// ─── ACTIVATE ───────────────────────────────────────────────────────────────
// Limpia caches de versiones anteriores.
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k.startsWith('sistema-') && !k.endsWith(VERSION))
          .map((k) => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ─── FETCH ──────────────────────────────────────────────────────────────────
// Estrategias por tipo de request.
self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Solo GET (POSTs, etc. siempre van a la red sin cache)
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // 1) Emergencia URL (Cloudinary, cross-origin): stale-while-revalidate
  if (EMERGENCIA_URL && req.url === EMERGENCIA_URL) {
    event.respondWith(staleWhileRevalidate(req, EXTERNAL_CACHE));
    return;
  }

  // 2) Same-origin assets (/static/, /media/): cache-first
  if (url.origin === self.location.origin && (
    url.pathname.startsWith('/static/') ||
    url.pathname.startsWith('/media/') ||
    url.pathname === '/manifest.webmanifest'
  )) {
    event.respondWith(cacheFirst(req, SHELL_CACHE));
    return;
  }

  // 3) Navegaciones (paginas HTML): network-first con fallback a cache
  const isNavigation = (
    req.mode === 'navigate' ||
    (req.headers.get('accept') || '').includes('text/html')
  );
  if (isNavigation) {
    event.respondWith(networkFirstWithFallback(req, PAGES_CACHE));
    return;
  }

  // 4) CDNs externos (jsdelivr, unpkg, google fonts): cache-first best-effort
  if (url.origin !== self.location.origin) {
    event.respondWith(cacheFirst(req, EXTERNAL_CACHE));
    return;
  }
});

// ─── ESTRATEGIAS ────────────────────────────────────────────────────────────
async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(req);
  if (cached) return cached;
  try {
    const resp = await fetch(req);
    if (resp && resp.ok) cache.put(req, resp.clone());
    return resp;
  } catch (e) {
    return cached || new Response('', { status: 504, statusText: 'Offline' });
  }
}

async function networkFirstWithFallback(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const resp = await fetch(req);
    // Solo cachear respuestas 2xx para no guardar errores
    if (resp && resp.ok && resp.type !== 'opaqueredirect') {
      cache.put(req, resp.clone()).catch(() => {});
    }
    return resp;
  } catch (e) {
    const cached = await cache.match(req);
    if (cached) return cached;
    // Fallback final: pagina offline con boton al catalogo de emergencia
    return new Response(OFFLINE_FALLBACK_HTML, {
      status: 200,
      headers: { 'Content-Type': 'text/html; charset=utf-8' }
    });
  }
}

async function staleWhileRevalidate(req, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(req);
  const fetchPromise = fetch(req).then((resp) => {
    if (resp && resp.ok) cache.put(req, resp.clone());
    return resp;
  }).catch(() => null);
  return cached || (await fetchPromise) || new Response('', { status: 504 });
}
"""


def _shell_assets(request):
    """Lista de URLs absolutas (en este origen) que precachear al instalar el SW.
    Son los archivos que cambian poco y que necesitamos sin red."""
    paths = [
        '/manifest.webmanifest',
        static('icons/app-icon.svg'),
        static('js/session_timeout.js'),
        static('js/form_lock.js'),
        static('js/image_compressor.js'),
    ]
    return [request.build_absolute_uri(p) for p in paths]


@csrf_exempt
@cache_control(max_age=0, no_cache=True, no_store=True, must_revalidate=True)
def service_worker(request):
    import json as _json
    body = (SERVICE_WORKER_JS_TEMPLATE
            .replace('%%CACHE_VERSION%%', SW_CACHE_VERSION)
            .replace('%%EMERGENCIA_URL%%', _emergencia_url())
            .replace('%%SHELL_ASSETS%%', _json.dumps(_shell_assets(request))))
    resp = HttpResponse(body, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    return resp
