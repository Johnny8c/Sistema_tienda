from django.db import migrations


def productos_a_catalogo(apps, schema_editor):
    """Agrupa productos existentes por nombre y crea un CatalogoProducto por cada nombre único."""
    Producto = apps.get_model('inventario', 'Producto')
    CatalogoProducto = apps.get_model('inventario', 'CatalogoProducto')

    nombres_vistos = {}
    for p in Producto.objects.all().order_by('id'):
        nombre = p.nombre.strip()
        if nombre not in nombres_vistos:
            cat = CatalogoProducto.objects.create(
                nombre=nombre,
                categoria='otro',
                precio_base=p.precio,
                activo=p.activo,
            )
            nombres_vistos[nombre] = cat
        p.catalogo = nombres_vistos[nombre]
        p.save(update_fields=['catalogo'])


def revertir(apps, schema_editor):
    CatalogoProducto = apps.get_model('inventario', 'CatalogoProducto')
    CatalogoProducto.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ('inventario', '0002_catalogoproducto'),
    ]

    operations = [
        migrations.RunPython(productos_a_catalogo, revertir),
    ]
