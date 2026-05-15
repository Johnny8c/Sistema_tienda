from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='usuario',
            name='cedula',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='usuario',
            name='telefono',
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name='usuario',
            name='direccion',
            field=models.TextField(blank=True),
        ),
    ]
