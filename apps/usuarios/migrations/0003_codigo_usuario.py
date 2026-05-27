from django.db import migrations, models


def asignar_codigos(apps, schema_editor):
    """Asigna códigos 01, 02, 03... a los usuarios existentes en orden de
    creación (por id ascendente). Sin esto la migración al agregar la columna
    como UNIQUE fallaría — todos los rows existentes quedarían con '' duplicado."""
    Usuario = apps.get_model('usuarios', 'Usuario')
    for i, u in enumerate(Usuario.objects.order_by('id'), start=1):
        u.codigo = f'{i:02d}'  # 01, 02, ..., 99
        u.save(update_fields=['codigo'])


def reverse_noop(apps, schema_editor):
    """No-op: si rollbackeamos, el campo se borra de todos modos."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0002_usuario_datos_contacto'),
    ]

    operations = [
        # 1. Agregamos el campo SIN unique=True y permitiendo blank, para que
        #    el ALTER TABLE no falle con los rows existentes.
        migrations.AddField(
            model_name='usuario',
            name='codigo',
            field=models.CharField(blank=True, default='', max_length=2),
            preserve_default=False,
        ),
        # 2. Rellenamos cada usuario con un código único en orden de creación.
        migrations.RunPython(asignar_codigos, reverse_code=reverse_noop),
        # 3. Ahora sí endurecemos: NOT NULL implícito por default + UNIQUE.
        migrations.AlterField(
            model_name='usuario',
            name='codigo',
            field=models.CharField(max_length=2, unique=True),
        ),
    ]
