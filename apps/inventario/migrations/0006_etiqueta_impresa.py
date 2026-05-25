from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0005_categoria_administrable'),
    ]

    operations = [
        migrations.CreateModel(
            name='EtiquetaImpresa',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo_barras', models.CharField(db_index=True, max_length=100, unique=True)),
                ('total_impresas', models.PositiveIntegerField(default=0)),
                ('ultima_impresion', models.DateTimeField()),
            ],
            options={
                'verbose_name': 'Etiqueta impresa',
                'verbose_name_plural': 'Etiquetas impresas',
                'ordering': ['-ultima_impresion'],
            },
        ),
    ]
