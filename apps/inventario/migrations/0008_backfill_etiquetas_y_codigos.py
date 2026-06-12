"""Saneamiento de datos para que el conteo de etiquetas no pierda unidades.

1) Registros de EtiquetaImpresa con stock_al_imprimir=NULL (impresos antes
   de que existiera el snapshot, o importados del historial viejo de
   localStorage): se fijan al stock ACTUAL de la variante. Es la misma
   interpretación que ya hacía el frontend ("todo lo de hoy está impreso"),
   pero concreta — así los aumentos de stock posteriores sí cuentan como
   etiquetas faltantes. Con NULL, reponer stock no generaba etiquetas
   (el caso real de "100 prendas ingresadas, 95 etiquetas").

2) Variantes sin código de barras: se les asigna TDA-{id:06d}. Una variante
   sin código es invisible en la pantalla de etiquetas.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    Producto = apps.get_model('inventario', 'Producto')
    EtiquetaImpresa = apps.get_model('inventario', 'EtiquetaImpresa')

    # 2) primero los códigos, para que el paso 1 encuentre la variante
    codigos_existentes = set(
        Producto.objects.exclude(codigo_barras__isnull=True)
        .exclude(codigo_barras='')
        .values_list('codigo_barras', flat=True)
    )
    sin_codigo = Producto.objects.filter(codigo_barras__isnull=True) | \
        Producto.objects.filter(codigo_barras='')
    for p in sin_codigo:
        codigo = f'TDA-{p.id:06d}'
        # Por si otro registro ya usa ese código (no debería: los códigos se
        # generan con el id propio), evitar romper el unique.
        sufijo = 2
        while codigo in codigos_existentes:
            codigo = f'TDA-{p.id:06d}-{sufijo}'
            sufijo += 1
        p.codigo_barras = codigo
        p.save(update_fields=['codigo_barras'])
        codigos_existentes.add(codigo)

    # 1) snapshots NULL → stock actual de la variante (0 si el código ya no
    # corresponde a ninguna variante)
    stocks = dict(Producto.objects.values_list('codigo_barras', 'stock'))
    for ei in EtiquetaImpresa.objects.filter(stock_al_imprimir__isnull=True):
        ei.stock_al_imprimir = stocks.get(ei.codigo_barras, 0)
        ei.save(update_fields=['stock_al_imprimir'])


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0007_etiqueta_stock_al_imprimir'),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
