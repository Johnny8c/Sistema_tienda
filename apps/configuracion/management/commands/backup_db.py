"""
Backup automatico de la base de datos a Cloudinary.

Usa Django dumpdata para generar un JSON con todos los datos del negocio,
lo comprime con gzip y lo sube a Cloudinary como recurso 'authenticated'
(requiere credenciales para descargar; no es publico). Opcionalmente borra
backups anteriores a N dias.

Uso:
    python manage.py backup_db
    python manage.py backup_db --cleanup-days 30
    python manage.py backup_db --dry-run

Cron en Railway (todas las madrugadas 03:00 America/Guayaquil):
    0 8 * * *   python manage.py backup_db --cleanup-days 30
    (08:00 UTC = 03:00 America/Guayaquil)
"""
import gzip
import os
import tempfile
from datetime import datetime, timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


# Tablas que NO se incluyen en el backup:
#  - contenttypes / auth.permission: las recrea Django con migrate.
#  - admin.logentry: log interno del admin, no es data de negocio.
#  - sessions.session: cookies de sesion, no tiene sentido restaurar.
EXCLUDE_APPS = [
    'contenttypes',
    'auth.permission',
    'admin.logentry',
    'sessions.session',
]


class Command(BaseCommand):
    help = 'Backup de la BD comprimido y subido a Cloudinary (privado).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup-days', type=int, default=30,
            help='Borra backups anteriores a N dias (default 30, 0=no borrar).'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Genera el backup pero no sube ni borra nada.'
        )

    def handle(self, *args, **opts):
        # Cloudinary debe estar configurado (settings.py lo configura cuando
        # CLOUDINARY_URL esta en el entorno).
        try:
            import cloudinary
            import cloudinary.uploader
            import cloudinary.api
        except ImportError:
            raise CommandError('Falta el paquete cloudinary. Esta en requirements.txt?')

        if not cloudinary.config().cloud_name:
            raise CommandError(
                'CLOUDINARY_URL no configurado. Sin destino para el backup.'
            )

        cleanup_days = opts['cleanup_days']
        dry_run = opts['dry_run']

        # 1. Generar dump JSON con dumpdata
        self.stdout.write('Generando dump de la BD...')
        buf = StringIO()
        try:
            call_command(
                'dumpdata',
                '--natural-foreign',
                '--natural-primary',
                *[f'--exclude={app}' for app in EXCLUDE_APPS],
                stdout=buf,
            )
        except Exception as e:
            raise CommandError(f'dumpdata fallo: {e}')

        data = buf.getvalue()
        if not data or len(data) < 10:
            raise CommandError('dumpdata devolvio vacio. Algo esta mal.')
        self.stdout.write(f'  Dump generado: {len(data):,} bytes')

        # 2. Comprimir a un archivo temporal
        now = timezone.now()
        stamp = now.strftime('%Y-%m-%d_%H%M%S')
        public_id = f'backup_{stamp}'

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.json.gz', delete=False) as tmp:
                tmp_path = tmp.name

            with gzip.open(tmp_path, 'wt', encoding='utf-8') as gz:
                gz.write(data)
            size_kb = os.path.getsize(tmp_path) / 1024
            self.stdout.write(f'  Comprimido: {size_kb:.1f} KB')

            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f'[dry-run] No se sube. Habria subido como: backups/{public_id}'
                ))
            else:
                # 3. Subir a Cloudinary como recurso autenticado
                self.stdout.write('Subiendo a Cloudinary...')
                result = cloudinary.uploader.upload(
                    tmp_path,
                    resource_type='raw',
                    type='authenticated',
                    folder='backups',
                    public_id=public_id,
                    overwrite=False,
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  Backup subido: backups/{public_id}'
                ))
                self.stdout.write(f'  URL firmada: {result.get("secure_url", "")}')

        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        # 4. Limpieza de backups antiguos
        if cleanup_days > 0:
            self._cleanup(cleanup_days, dry_run, cloudinary)

        self.stdout.write(self.style.SUCCESS('Backup terminado.'))

    def _cleanup(self, days, dry_run, cloudinary):
        cutoff = timezone.now() - timedelta(days=days)
        self.stdout.write(f'Buscando backups anteriores a {cutoff.date()}...')

        to_delete = []
        next_cursor = None
        while True:
            kwargs = {
                'type': 'authenticated',
                'resource_type': 'raw',
                'prefix': 'backups/',
                'max_results': 100,
            }
            if next_cursor:
                kwargs['next_cursor'] = next_cursor
            try:
                resp = cloudinary.api.resources(**kwargs)
            except Exception as e:
                self.stderr.write(self.style.WARNING(
                    f'No se pudo listar backups (skip cleanup): {e}'
                ))
                return

            for r in resp.get('resources', []):
                created = r.get('created_at')
                if not created:
                    continue
                created_dt = datetime.fromisoformat(
                    created.replace('Z', '+00:00')
                )
                if created_dt < cutoff:
                    to_delete.append(r['public_id'])

            next_cursor = resp.get('next_cursor')
            if not next_cursor:
                break

        if not to_delete:
            self.stdout.write('  Nada que limpiar.')
            return

        self.stdout.write(f'  Backups a borrar: {len(to_delete)}')
        if dry_run:
            for pid in to_delete:
                self.stdout.write(f'    - {pid}')
            self.stdout.write(self.style.WARNING('[dry-run] No se borra nada.'))
            return

        try:
            cloudinary.api.delete_resources(
                to_delete,
                resource_type='raw',
                type='authenticated',
            )
            self.stdout.write(self.style.SUCCESS(
                f'  {len(to_delete)} backups antiguos eliminados.'
            ))
        except Exception as e:
            self.stderr.write(self.style.WARNING(
                f'No se pudo borrar algunos backups: {e}'
            ))
