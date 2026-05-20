"""
Genera un catalogo HTML estatico de emergencia y lo sube a Cloudinary
como recurso publico. Es el "modo offline" para el cajero: si el sistema
o el internet de la tienda se cae, abre la URL publica en el celular y
consulta precios + stock.

URL resultante (estable):
    https://res.cloudinary.com/<cloud_name>/raw/upload/emergencia/catalogo.html

Uso:
    python manage.py generar_emergencia
    python manage.py generar_emergencia --dry-run

Cron: encadenado al backup_db (en el mismo servicio backup-cron).
"""
import html
import json
import os
import tempfile

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


PUBLIC_ID = 'emergencia/catalogo'


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>{titulo}</title>
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#F3F4F6;color:#111827;font-size:15px;line-height:1.4}}
  header{{background:{color};color:#fff;padding:14px 16px;position:sticky;top:0;z-index:10;box-shadow:0 2px 8px rgba(0,0,0,.12)}}
  header .titulo{{font-size:18px;font-weight:800;letter-spacing:.3px}}
  header .sub{{font-size:12px;opacity:.85;margin-top:2px}}
  .banner{{background:#FEF3C7;color:#92400E;padding:10px 16px;font-size:13px;border-bottom:1px solid #FBBF24}}
  .banner b{{font-weight:800}}
  .search{{padding:12px 16px;background:#fff;border-bottom:1px solid #E5E7EB;position:sticky;top:60px;z-index:9}}
  .search input{{width:100%;padding:12px 14px;border:1.5px solid #D1D5DB;border-radius:10px;font-size:16px;outline:none}}
  .search input:focus{{border-color:{color}}}
  .stats{{padding:8px 16px;color:#6B7280;font-size:12px;background:#fff;border-bottom:1px solid #E5E7EB}}
  .stats b{{color:#111827;font-weight:700}}
  .empty{{padding:40px 20px;text-align:center;color:#6B7280}}
  .empty i{{display:block;font-size:36px;margin-bottom:8px;opacity:.4}}
  .list{{padding:8px}}
  .card{{background:#fff;border-radius:10px;padding:12px 14px;margin-bottom:8px;box-shadow:0 1px 2px rgba(0,0,0,.05);border:1px solid #E5E7EB}}
  .card .nombre{{font-weight:700;font-size:15px;color:#111827;line-height:1.25;margin-bottom:4px}}
  .card .meta{{font-size:12px;color:#6B7280;display:flex;flex-wrap:wrap;gap:8px;margin-bottom:6px}}
  .card .meta span{{display:inline-flex;align-items:center;gap:4px}}
  .card .meta .codigo{{font-family:'SF Mono','Consolas',monospace;background:#F3F4F6;padding:1px 6px;border-radius:4px;font-size:11px;color:#374151}}
  .card .talla{{background:#111827;color:#fff;padding:1px 8px;border-radius:4px;font-weight:700;font-size:11px;letter-spacing:.3px;text-transform:uppercase}}
  .card .color-dot{{width:10px;height:10px;border-radius:50%;border:1px solid #ccc;display:inline-block;vertical-align:middle;margin-right:2px}}
  .card .precio-row{{display:flex;align-items:center;justify-content:space-between;margin-top:4px;padding-top:6px;border-top:1px dashed #E5E7EB}}
  .card .precio{{font-size:18px;font-weight:800;color:#111827;letter-spacing:-.3px}}
  .card .stock{{font-size:12px;font-weight:700;padding:3px 8px;border-radius:6px}}
  .card .stock.ok{{background:#D1FAE5;color:#065F46}}
  .card .stock.bajo{{background:#FEF3C7;color:#92400E}}
  .card .stock.cero{{background:#FEE2E2;color:#991B1B}}
  footer{{padding:20px;text-align:center;color:#9CA3AF;font-size:11px}}
  footer .negocio{{color:#6B7280;font-weight:600;margin-bottom:4px}}
  @media (min-width:600px){{
    .list{{padding:12px}}
    .card{{padding:14px 16px}}
  }}
</style>
</head>
<body>
<header>
  <div class="titulo">{nombre_negocio}</div>
  <div class="sub">{telefono_html}{slogan_html}</div>
</header>
<div class="banner">
  <b>Modo emergencia</b> · Consulta de precios offline · Actualizado: {fecha_actualiza}
</div>
<div class="search">
  <input id="q" type="search" placeholder="Buscar por nombre, codigo, talla o color..." autocomplete="off">
</div>
<div class="stats" id="stats"></div>
<div class="list" id="list"></div>
<footer>
  <div class="negocio">{nombre_negocio}</div>
  Catalogo generado: {fecha_actualiza}<br>
  Solo lectura. No se registran ventas desde esta pantalla.
</footer>
<script>
const COLORES = {{
  'rojo':'#DC2626','verde':'#10B981','azul':'#3B82F6','amarillo':'#FBBF24',
  'negro':'#111827','blanco':'#F9FAFB','gris':'#6B7280','rosa':'#EC4899',
  'morado':'#8B5CF6','naranja':'#F97316','marron':'#7C2D12','cafe':'#7C2D12',
  'celeste':'#38BDF8','turquesa':'#14B8A6','beige':'#D6C9A8','dorado':'#D4AF37',
  'plateado':'#C0C0C0','crema':'#FFFDD0','vino':'#7F1D1D','fucsia':'#D946EF',
}};
const STOCK_MIN = {stock_min};
const PRODS = {productos_json};

function colorDot(c){{
  const k = (c||'').toLowerCase().trim();
  const hex = COLORES[k] || '#9CA3AF';
  return `<span class="color-dot" style="background:${{hex}}"></span>`;
}}

function stockClass(s){{
  if(s<=0) return 'cero';
  if(s<=STOCK_MIN) return 'bajo';
  return 'ok';
}}

function render(filtro){{
  filtro = (filtro||'').toLowerCase().trim();
  const list = document.getElementById('list');
  const stats = document.getElementById('stats');
  const matched = PRODS.filter(p => {{
    if(!filtro) return true;
    return (
      (p.n && p.n.toLowerCase().includes(filtro)) ||
      (p.c && p.c.toLowerCase().includes(filtro)) ||
      (p.t && p.t.toLowerCase().includes(filtro)) ||
      (p.col && p.col.toLowerCase().includes(filtro))
    );
  }});

  if(matched.length === 0){{
    list.innerHTML = '<div class="empty">Sin coincidencias para "'+escapeHtml(filtro)+'"</div>';
    stats.innerHTML = '<b>0</b> resultados';
    return;
  }}

  stats.innerHTML = `<b>${{matched.length}}</b> de ${{PRODS.length}} productos`;
  list.innerHTML = matched.map(p => {{
    const code = p.c ? `<span class="codigo">${{escapeHtml(p.c)}}</span>` : '';
    const talla = p.t ? `<span class="talla">${{escapeHtml(p.t)}}</span>` : '';
    const color = p.col ? `<span>${{colorDot(p.col)}}${{escapeHtml(p.col)}}</span>` : '';
    const sCls = stockClass(p.s);
    const sTxt = p.s<=0 ? 'SIN STOCK' : (p.s+' u');
    return `<div class="card">
      <div class="nombre">${{escapeHtml(p.n)}}</div>
      <div class="meta">${{code}}${{talla}}${{color}}</div>
      <div class="precio-row">
        <div class="precio">$${{p.p}}</div>
        <div class="stock ${{sCls}}">${{sTxt}}</div>
      </div>
    </div>`;
  }}).join('');
}}

function escapeHtml(s){{
  return String(s).replace(/[&<>"']/g, m => ({{
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }})[m]);
}}

document.getElementById('q').addEventListener('input', e => render(e.target.value));
render('');
</script>
</body>
</html>
"""


class Command(BaseCommand):
    help = 'Genera catalogo HTML de emergencia y lo sube publico a Cloudinary.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Genera el HTML pero no sube nada.'
        )

    def handle(self, *args, **opts):
        try:
            import cloudinary
            import cloudinary.uploader
        except ImportError:
            raise CommandError('Falta el paquete cloudinary.')

        if not cloudinary.config().cloud_name:
            raise CommandError('CLOUDINARY_URL no configurado.')

        from apps.configuracion.models import ConfiguracionGeneral
        from apps.inventario.models import Producto

        cfg = ConfiguracionGeneral.get_singleton()
        stock_min = cfg.stock_minimo_alerta or 5

        # Productos activos con codigo (los que pueden venderse y consultarse)
        qs = (Producto.objects
              .filter(activo=True)
              .select_related('catalogo')
              .order_by('nombre', 'talla', 'color'))

        productos = []
        for p in qs:
            stock_disp = max(0, p.stock - p.stock_reservado)
            productos.append({
                'n': p.nombre or (p.catalogo.nombre if p.catalogo_id else ''),
                'c': p.codigo_barras or '',
                't': p.talla or '',
                'col': p.color or '',
                'p': f'{float(p.precio):.2f}',
                's': stock_disp,
            })

        self.stdout.write(f'Productos a publicar: {len(productos)}')
        if not productos:
            self.stdout.write(self.style.WARNING(
                'No hay productos activos. Genero el HTML vacio igual.'
            ))

        productos_json = json.dumps(productos, ensure_ascii=False, separators=(',', ':'))
        now = timezone.localtime()
        fecha_str = now.strftime('%d/%m/%Y %H:%M')

        nombre = cfg.nombre_negocio or 'Sistema Tienda'
        slogan_html = ''
        if cfg.slogan:
            slogan_html = ' · ' + html.escape(cfg.slogan)
        telefono_html = ''
        if cfg.telefono:
            telefono_html = html.escape(cfg.telefono)

        html_final = HTML_TEMPLATE.format(
            titulo=html.escape(f'{nombre} — Modo emergencia'),
            nombre_negocio=html.escape(nombre),
            telefono_html=telefono_html,
            slogan_html=slogan_html,
            color=cfg.color_primario or '#4F46E5',
            fecha_actualiza=fecha_str,
            stock_min=stock_min,
            productos_json=productos_json,
        )

        size_kb = len(html_final.encode('utf-8')) / 1024
        self.stdout.write(f'HTML generado: {size_kb:.1f} KB')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'[dry-run] No se sube. Habria subido como: {PUBLIC_ID}.html'
            ))
            return

        # Escribir a temp file para upload
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.html', delete=False, encoding='utf-8'
            ) as tmp:
                tmp.write(html_final)
                tmp_path = tmp.name

            self.stdout.write('Subiendo a Cloudinary (publico)...')
            result = cloudinary.uploader.upload(
                tmp_path,
                resource_type='raw',
                type='upload',  # publico (no requiere firma)
                public_id=PUBLIC_ID,
                overwrite=True,
                invalidate=True,  # purge CDN cache
                format='html',
            )
            url = result.get('secure_url', '')
            self.stdout.write(self.style.SUCCESS(f'  Catalogo subido.'))
            self.stdout.write(f'  URL publica: {url}')

        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        self.stdout.write(self.style.SUCCESS('Modo emergencia listo.'))
