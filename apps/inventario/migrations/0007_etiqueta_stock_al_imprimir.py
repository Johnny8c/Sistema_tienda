from django.db import migrations, models
from django.utils import timezone


def backfill_stock_al_imprimir(apps, schema_editor):
    """Para cada EtiquetaImpresa existente, setea stock_al_imprimir =
    stock_actual - cantidad_comprada_hoy. Esto produce 2 efectos deseados:

    1. Lo que se compró HOY (vía Compras del módulo Proveedores) queda como
       "faltante" → aparece en pendientes para imprimir.
    2. El resto del stock que ya estaba antes de hoy queda como "ya impreso"
       → mantiene el progreso visual del usuario, no resetea todo a 0.

    Limitación conocida: solo detecta stock añadido vía Compras (proveedor).
    Ajustes manuales del stock (botón +stock en inventario) no quedan en
    histórico, así que esos no se compensan automáticamente."""
    from django.db.models import Sum

    EtiquetaImpresa = apps.get_model('inventario', 'EtiquetaImpresa')
    Producto = apps.get_model('inventario', 'Producto')
    ItemCompra = apps.get_model('proveedores', 'ItemCompra')

    hoy = timezone.localdate()

    # Stock actual de cada producto con código de barras
    stock_actual = {
        p.codigo_barras: p.stock
        for p in Producto.objects.exclude(codigo_barras='').exclude(codigo_barras__isnull=True)
    }

    # Cantidad comprada HOY por código de barras
    comprado_hoy = {}
    for row in (ItemCompra.objects
                .filter(compra__creado_en__date=hoy)
                .values('producto__codigo_barras')
                .annotate(t=Sum('cantidad'))):
        codigo = row['producto__codigo_barras']
        if codigo:
            comprado_hoy[codigo] = row['t'] or 0

    actualizadas = 0
    for ei in EtiquetaImpresa.objects.filter(stock_al_imprimir__isnull=True):
        actual = stock_actual.get(ei.codigo_barras, 0)
        hoy_nuevo = comprado_hoy.get(ei.codigo_barras, 0)
        # "Imprimí cuando había (actual - hoy_nuevo)". Clamp en 0 por si la
        # resta da negativo por algún caso raro.
        ei.stock_al_imprimir = max(0, actual - hoy_nuevo)
        ei.save(update_fields=['stock_al_imprimir'])
        actualizadas += 1


def reverse_noop(apps, schema_editor):
    """No-op: si rollbackeamos, el campo se borra de todos modos."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0006_etiqueta_impresa'),
        ('proveedores', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='etiquetaimpresa',
            name='stock_al_imprimir',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_stock_al_imprimir, reverse_code=reverse_noop),
    ]
