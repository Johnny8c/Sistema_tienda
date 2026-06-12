"""Diagnostica por qué una etiqueta escaneada 'no existe' o 'no tiene stock'.

Uso (en producción, p. ej. Railway):
    python manage.py diagnosticar_codigo TDA-001401
    python manage.py diagnosticar_codigo TDA-001401 --nombre "galleta"

Responde, para un código de barras impreso en una etiqueta física:
  - si la variante existe y en qué estado está (activa, stock, reservas)
  - si fue desactivada (el POS solo ve variantes activas)
  - si el id del código apunta a una variante cuyo código ya no coincide
    (señal de datos re-importados o código regenerado)
  - qué variantes parecidas SÍ están activas y con stock (posibles duplicados
    del mismo producto creados después, con otro código)
  - el historial de impresión de esa etiqueta
"""
import re

from django.core.management.base import BaseCommand

from apps.inventario.models import Producto, EtiquetaImpresa


class Command(BaseCommand):
    help = 'Rastrea un código de barras de etiqueta que no aparece al escanear.'

    def add_arguments(self, parser):
        parser.add_argument('codigo', help='Código impreso en la etiqueta, p. ej. TDA-001401')
        parser.add_argument('--nombre', default='',
                            help='Texto del nombre en la etiqueta, para buscar variantes parecidas')

    def _describir(self, p, etiqueta=''):
        cat = p.catalogo
        self.stdout.write(
            f'  {etiqueta}id={p.pk}  codigo={p.codigo_barras or "(sin código)"}  '
            f'"{p.nombre}"  talla={p.talla or "-"}  color={p.color or "-"}'
        )
        self.stdout.write(
            f'      stock={p.stock}  reservado={p.stock_reservado}  '
            f'disponible={p.stock_disponible}  '
            f'variante_activa={"SÍ" if p.activo else "NO"}  '
            f'producto_activo={"SÍ" if (cat and cat.activo) else ("NO" if cat else "sin catálogo")}  '
            f'creada={p.creado_en:%Y-%m-%d %H:%M}'
        )

    def handle(self, *args, **opts):
        codigo = opts['codigo'].strip()
        nombre = opts['nombre'].strip()
        w = self.stdout.write

        w(self.style.MIGRATE_HEADING(f'--- Diagnóstico del código {codigo} ---'))

        # 1) ¿Existe una variante con ese código (activa o no)?
        p = Producto.objects.select_related('catalogo').filter(codigo_barras=codigo).first()
        if p:
            self._describir(p)
            if not p.activo or (p.catalogo and not p.catalogo.activo):
                w(self.style.WARNING(
                    '  -> La variante (o su producto) está DESACTIVADA. El POS y la '
                    'consulta de precios solo ven variantes activas: por eso el '
                    'escaneo dice que no existe. Si la prenda sigue a la venta, '
                    'el stock seguramente se volvió a ingresar como una variante '
                    'nueva con OTRO código (ver "parecidas" abajo).'
                ))
            elif p.stock_disponible <= 0:
                w(self.style.WARNING(
                    f'  -> La variante existe pero sin stock disponible '
                    f'(stock={p.stock}, reservado={p.stock_reservado}). Si en la '
                    'percha sí hay prendas, el stock físico se ingresó en otra '
                    'variante (ver "parecidas" abajo) o no se registró.'
                ))
            else:
                w(self.style.SUCCESS(
                    '  -> La variante está activa y con stock. Si el escáner no la '
                    'encuentra, el problema es de lectura (layout del teclado del '
                    'lector: revisar guiones/apóstrofes).'
                ))
            if not nombre:
                nombre = p.nombre
        else:
            w('  No existe NINGUNA variante con ese código (ni inactiva).')
            # 2) El código lleva el id de la variante: TDA-001401 -> id 1401
            m = re.search(r'(\d+)$', codigo)
            if m:
                pid = int(m.group(1))
                por_id = Producto.objects.select_related('catalogo').filter(pk=pid).first()
                if por_id:
                    w(f'  La variante id={pid} (de la que salió este código) hoy es:')
                    self._describir(por_id)
                    if (por_id.codigo_barras or '') != codigo:
                        w(self.style.WARNING(
                            f'  -> Su código actual es {por_id.codigo_barras!r}, NO {codigo!r}. '
                            'El código fue cambiado o regenerado después de imprimir '
                            'la etiqueta (p. ej. re-importación de datos).'
                        ))
                    if not nombre:
                        nombre = por_id.nombre
                else:
                    w(self.style.WARNING(
                        f'  -> Tampoco existe la variante id={pid}: fue BORRADA de la '
                        'base (no solo desactivada) o la base actual no es la misma '
                        'donde se imprimió la etiqueta.'
                    ))

        # 3) Historial de impresión de ese código
        ei = EtiquetaImpresa.objects.filter(codigo_barras=codigo).first()
        if ei:
            w(f'  Historial: se imprimieron {ei.total_impresas} etiqueta(s) de este '
              f'código, última vez {ei.ultima_impresion:%Y-%m-%d %H:%M} '
              f'(snapshot stock_al_imprimir={ei.stock_al_imprimir}).')
        else:
            w('  Sin historial de impresión en el servidor para este código '
              '(pudo imprimirse antes de que el historial fuera compartido).')

        # 4) Variantes parecidas activas (posibles duplicados con otro código)
        if nombre:
            palabras = [t for t in re.split(r'\s+', nombre) if len(t) >= 4][:3]
            qs = Producto.objects.select_related('catalogo').filter(activo=True)
            for t in palabras:
                qs = qs.filter(nombre__icontains=t)
            parecidas = list(qs.exclude(codigo_barras=codigo)[:15])
            if parecidas:
                w(f'  Variantes ACTIVAS parecidas a "{nombre}":')
                for v in parecidas:
                    self._describir(v)
                w(self.style.NOTICE(
                    '  -> Si una de estas es la misma prenda física, hay un duplicado: '
                    'la etiqueta vieja apunta al registro viejo y el stock vive en el '
                    'nuevo. Solución: pasar el stock a UNA variante (ajustar stock), '
                    'desactivar la otra y reimprimir etiquetas, o re-etiquetar las '
                    'prendas con el código nuevo.'
                ))
            else:
                w(f'  No hay variantes activas parecidas a "{nombre}".')
        else:
            w('  (Pasa --nombre "texto de la etiqueta" para buscar variantes parecidas.)')
