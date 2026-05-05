"""
RIDE (Representación Impresa del Documento Electrónico) en PDF.
Puerto de ridePdf.js usando reportlab + python-barcode.
"""
import io
from datetime import datetime
from decimal import Decimal

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor

import barcode
from barcode.writer import ImageWriter

A4_W, A4_H = A4
MARGIN = 36
COL_W  = A4_W - MARGIN * 2


def _fmt2(n):
    return f'${Decimal(str(n or 0)):.2f}'


def _fmt_qty(n):
    v = Decimal(str(n or 0))
    if v == v.to_integral_value():
        return str(int(v))
    return str(v.normalize())


def _generar_barcode_png(clave_acceso):
    if not clave_acceso:
        return None
    try:
        Code128 = barcode.get_barcode_class('code128')
        bio = io.BytesIO()
        bc = Code128(clave_acceso, writer=ImageWriter())
        bc.write(bio, options={
            'write_text':       False,
            'module_height':    8.0,
            'quiet_zone':       2.0,
        })
        bio.seek(0)
        return bio
    except Exception as e:
        print(f'[RIDE] Error generando código de barras: {e}')
        return None


def _draw_box(c, x, y, w, h, fill=None, stroke=None, radius=4):
    if fill:
        c.setFillColor(HexColor(fill))
        c.roundRect(x, y, w, h, radius, stroke=0, fill=1)
    if stroke:
        c.setStrokeColor(HexColor(stroke))
        c.setLineWidth(0.5)
        c.roundRect(x, y, w, h, radius, stroke=1, fill=0)


def _draw_line(c, x1, y1, x2, y2, color='#CCCCCC'):
    c.setStrokeColor(HexColor(color))
    c.setLineWidth(0.5)
    c.line(x1, y1, x2, y2)


def _text(c, x, y, text, *, font='Helvetica', size=8, color='#111111', max_w=None, align='left'):
    c.setFont(font, size)
    c.setFillColor(HexColor(color))
    if max_w and align == 'right':
        c.drawRightString(x + max_w, y, str(text))
    elif max_w and align == 'center':
        c.drawCentredString(x + max_w / 2, y, str(text))
    else:
        c.drawString(x, y, str(text))


def generar_ride_pdf(factura, items, configuracion, cliente) -> bytes:
    """
    Genera el RIDE en PDF y devuelve los bytes.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    # En reportlab y=0 está abajo. Vamos a usar coordenadas "Y desde arriba".
    def Y(top_offset):
        return A4_H - top_offset

    es_contingencia = bool(factura.es_contingencia)
    ambiente_label  = 'PRODUCCIÓN' if (configuracion.ambiente == 'produccion') else 'PRUEBAS'

    # ── ENCABEZADO ───────────────────────────────────────────────
    header_top = MARGIN
    header_h   = 120
    left_w     = int(COL_W * 0.55)
    right_w    = COL_W - left_w - 8
    right_x    = MARGIN + left_w + 8

    _draw_box(c, MARGIN, Y(header_top + header_h), left_w, header_h, stroke='#DDDDDD')
    _draw_box(c, right_x, Y(header_top + header_h), right_w, header_h, stroke='#DDDDDD')

    # Razón social
    _text(c, MARGIN + 8, Y(header_top + 18), configuracion.razon_social or 'EMISOR',
          font='Helvetica-Bold', size=11)
    if configuracion.nombre_comercial and configuracion.nombre_comercial != configuracion.razon_social:
        _text(c, MARGIN + 8, Y(header_top + 32), configuracion.nombre_comercial,
              font='Helvetica', size=9, color='#444444')
    if configuracion.direccion:
        _text(c, MARGIN + 8, Y(header_top + 50), f'Dirección: {configuracion.direccion}',
              font='Helvetica', size=8, color='#555555')
    if configuracion.telefono:
        _text(c, MARGIN + 8, Y(header_top + 64), f'Teléfono: {configuracion.telefono}',
              font='Helvetica', size=8, color='#555555')

    # RUC banner
    _draw_box(c, right_x, Y(header_top + 28), right_w, 28, fill='#1E40AF', radius=4)
    _text(c, right_x, Y(header_top + 13), 'R.U.C.',
          font='Helvetica-Bold', size=8, color='#FFFFFF', max_w=right_w, align='center')
    _text(c, right_x, Y(header_top + 24), configuracion.ruc or '—',
          font='Helvetica-Bold', size=11, color='#FFFFFF', max_w=right_w, align='center')

    # FACTURA + número
    _text(c, right_x, Y(header_top + 40), 'FACTURA',
          font='Helvetica-Bold', size=8, color='#333333', max_w=right_w, align='center')
    _text(c, right_x, Y(header_top + 52), factura.numero_factura or '—',
          font='Helvetica-Bold', size=10, max_w=right_w, align='center')

    # Núm. autorización
    _text(c, right_x + 4, Y(header_top + 64), 'NÚMERO DE AUTORIZACIÓN',
          font='Helvetica', size=6.5, color='#888888')
    _text(c, right_x + 4, Y(header_top + 76), factura.sri_numero_autorizacion or '—',
          font='Helvetica-Bold', size=7)

    # Fecha autorización + ambiente
    _text(c, right_x + 4, Y(header_top + 88), 'FECHA Y HORA AUTORIZACIÓN',
          font='Helvetica', size=6.5, color='#888888')
    fecha_aut = factura.sri_fecha_autorizacion.strftime('%d/%m/%Y %H:%M:%S') if factura.sri_fecha_autorizacion else '—'
    _text(c, right_x + 4, Y(header_top + 98), fecha_aut, font='Helvetica-Bold', size=7)

    half_r = (right_w - 8) / 2
    _text(c, right_x + 4 + half_r, Y(header_top + 88), 'AMBIENTE',
          font='Helvetica', size=6.5, color='#888888')
    amb_color = '#D97706' if ambiente_label == 'PRUEBAS' else '#15803D'
    _text(c, right_x + 4 + half_r, Y(header_top + 98), ambiente_label,
          font='Helvetica-Bold', size=7, color=amb_color)

    # Tipo emisión
    _text(c, right_x + 4, Y(header_top + 110), 'TIPO DE EMISIÓN',
          font='Helvetica', size=6.5, color='#888888')
    tipo_color = '#DC2626' if es_contingencia else '#111111'
    _text(c, right_x + 4, Y(header_top + 119), 'CONTINGENCIA' if es_contingencia else 'NORMAL',
          font='Helvetica-Bold', size=7, color=tipo_color)

    # ── CLAVE DE ACCESO + BARCODE ─────────────────────────────────
    clave_top   = header_top + header_h + 6
    barcode_png = _generar_barcode_png(factura.clave_acceso)
    barcode_h   = 40 if barcode_png else 0
    clave_box_h = 28 + barcode_h

    _draw_box(c, MARGIN, Y(clave_top + clave_box_h), COL_W, clave_box_h,
              fill='#F8FAFC', stroke='#DDDDDD')
    _text(c, MARGIN + 8, Y(clave_top + 12), 'CLAVE DE ACCESO',
          font='Helvetica', size=6.5, color='#888888')

    if barcode_png:
        from reportlab.lib.utils import ImageReader
        img = ImageReader(barcode_png)
        bw = COL_W - 16
        c.drawImage(img, MARGIN + 8, Y(clave_top + 14 + 28),
                    width=bw, height=28, preserveAspectRatio=False, mask='auto')
        _text(c, MARGIN + 8, Y(clave_top + clave_box_h - 4),
              factura.clave_acceso or '', font='Helvetica', size=6, color='#444444',
              max_w=COL_W - 16, align='center')
    else:
        _text(c, MARGIN + 8, Y(clave_top + 24), factura.clave_acceso or '—',
              font='Helvetica-Bold', size=7.5, color='#1E3A5F', max_w=COL_W - 16)

    # ── DATOS DEL COMPRADOR ───────────────────────────────────────
    buyer_top = clave_top + clave_box_h + 6
    buyer_h = 48
    _draw_box(c, MARGIN, Y(buyer_top + buyer_h), COL_W, buyer_h, stroke='#DDDDDD')

    col_b = COL_W / 3
    _text(c, MARGIN + 8, Y(buyer_top + 12), 'RAZÓN SOCIAL / NOMBRES Y APELLIDOS',
          font='Helvetica', size=6.5, color='#888888')
    _text(c, MARGIN + 8, Y(buyer_top + 24),
          (cliente.nombre or 'CONSUMIDOR FINAL').upper(),
          font='Helvetica-Bold', size=8.5)

    _text(c, MARGIN + col_b * 2 + 4, Y(buyer_top + 12), 'IDENTIFICACIÓN',
          font='Helvetica', size=6.5, color='#888888')
    _text(c, MARGIN + col_b * 2 + 4, Y(buyer_top + 24),
          cliente.cedula_ruc or '9999999999999', font='Helvetica-Bold', size=8.5)

    _draw_line(c, MARGIN + 8, Y(buyer_top + 30), MARGIN + COL_W - 8, Y(buyer_top + 30))
    _text(c, MARGIN + 8, Y(buyer_top + 40), 'FECHA DE EMISIÓN',
          font='Helvetica', size=6.5, color='#888888')
    fe = factura.fecha_emision
    if isinstance(fe, str):
        fe = datetime.fromisoformat(fe[:10]).date()
    fecha_str = f'{fe.day:02d}/{fe.month:02d}/{fe.year}'
    _text(c, MARGIN + 8, Y(buyer_top + 48), fecha_str, font='Helvetica-Bold', size=8)

    # ── TABLA DE ÍTEMS ─────────────────────────────────────────────
    table_top = buyer_top + buyer_h + 8
    headers   = ['Cód.', 'Descripción', 'Cant.', 'P. Unitario', 'Descuento', 'IVA', 'P. Total']
    col_w     = [30, 0, 48, 60, 50, 28, 60]
    col_w[1]  = COL_W - sum(col_w)

    _draw_box(c, MARGIN, Y(table_top + 16), COL_W, 16, fill='#1E40AF', radius=0)
    cx = MARGIN
    for i, h in enumerate(headers):
        align = 'left' if i == 1 else 'right' if i > 1 else 'center'
        _text(c, cx + 3, Y(table_top + 12), h,
              font='Helvetica-Bold', size=7, color='#FFFFFF',
              max_w=col_w[i] - 6, align=align)
        cx += col_w[i]

    row_top = table_top + 16
    items_list = list(items)
    for idx, item in enumerate(items_list):
        bg = '#FFFFFF' if idx % 2 == 0 else '#F1F5F9'
        _draw_box(c, MARGIN, Y(row_top + 16), COL_W, 16, fill=bg, radius=0)
        row = [
            str(item.orden or idx + 1).zfill(3),
            item.descripcion or '',
            _fmt_qty(item.cantidad),
            _fmt2(item.precio_unitario),
            _fmt2(item.descuento),
            'Sí' if item.aplica_iva else 'No',
            _fmt2(item.subtotal),
        ]
        cx = MARGIN
        for i, val in enumerate(row):
            align = 'left' if i == 1 else 'right' if i > 1 else 'center'
            _text(c, cx + 3, Y(row_top + 12), val,
                  font='Helvetica', size=7.5, max_w=col_w[i] - 6, align=align)
            cx += col_w[i]
        row_top += 16

    # Borde tabla completa
    _draw_box(c, MARGIN, Y(row_top), COL_W, row_top - table_top, stroke='#CCCCCC', radius=0)

    # ── TOTALES ────────────────────────────────────────────────────
    tot_w = 200
    tot_x = MARGIN + COL_W - tot_w
    tot_top = row_top + 8
    tot_rows = [
        ('Subtotal sin impuestos', _fmt2(Decimal(str(factura.subtotal_0 or 0)) + Decimal(str(factura.subtotal_iva or 0))), False),
        ('Descuento total',        '$0.00', False),
        (f'IVA {factura.iva_porcentaje or 15}%', _fmt2(factura.iva_valor), False),
        ('IMPORTE TOTAL',          _fmt2(factura.total), True),
    ]
    for i, (label, value, bold) in enumerate(tot_rows):
        ty = tot_top + i * 16
        if bold:
            _draw_box(c, tot_x, Y(ty + 16), tot_w, 16, fill='#1E40AF', radius=0)
        lc = '#FFFFFF' if bold else '#555555'
        vc = '#FFFFFF' if bold else '#111111'
        _text(c, tot_x + 4, Y(ty + 12), label,
              font='Helvetica-Bold' if bold else 'Helvetica',
              size=8, color=lc)
        _text(c, tot_x + 4, Y(ty + 12), value,
              font='Helvetica-Bold', size=8, color=vc,
              max_w=tot_w - 8, align='right')
        if not bold:
            _draw_line(c, tot_x, Y(ty + 16), tot_x + tot_w, Y(ty + 16))

    # ── NOTAS / CONTINGENCIA ──────────────────────────────────────
    foot_top = tot_top + len(tot_rows) * 16 + 12
    if factura.notas:
        _text(c, MARGIN, Y(foot_top + 8), f'Notas: {factura.notas}',
              font='Helvetica', size=7, color='#666666', max_w=COL_W)
        foot_top += 20

    if es_contingencia:
        _draw_box(c, MARGIN, Y(foot_top + 16), COL_W, 16, fill='#FEF3C7', radius=2)
        _text(c, MARGIN, Y(foot_top + 12),
              'COMPROBANTE EMITIDO EN MODO CONTINGENCIA — Sujeto a autorización posterior por el SRI',
              font='Helvetica-Bold', size=7, color='#92400E', max_w=COL_W, align='center')

    # Pie
    footer_y = MARGIN + 16
    _draw_line(c, MARGIN, footer_y, MARGIN + COL_W, footer_y)
    _text(c, MARGIN, footer_y - 8,
          f'Documento generado por Sistema Tienda | {datetime.now().strftime("%d/%m/%Y %H:%M:%S")}',
          font='Helvetica', size=6.5, color='#AAAAAA', max_w=COL_W, align='center')

    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()
