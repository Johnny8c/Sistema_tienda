"""
Reintenta autorizar facturas en estado EMITIDA o en contingencia.
Útil cuando el SRI estuvo caído y ahora vuelve a estar disponible.

Uso:
    python manage.py reintentar_sri
    python manage.py reintentar_sri --max-edad-horas 48
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Re-consulta al SRI por facturas EMITIDAs o en contingencia que no quedaron AUTORIZADAS.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--max-edad-horas', type=int, default=72,
            help='Solo procesa facturas creadas en las últimas N horas (default 72).'
        )
        parser.add_argument(
            '--limit', type=int, default=200,
            help='Máximo de facturas a procesar en una corrida (default 200).'
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra qué se procesaría sin tocar el SRI.'
        )

    def handle(self, *args, **opts):
        from apps.facturacion.models import FacturaSRI, ConfiguracionSRI
        from apps.facturacion.services.sri.sri_client import consultar_autorizacion

        cfg = ConfiguracionSRI.get_singleton()
        if not cfg or not cfg.cert_configurado:
            self.stderr.write(self.style.ERROR(
                'No hay configuración SRI o certificado cargado. Abortando.'
            ))
            return

        edad_limite = timezone.now() - timedelta(hours=opts['max_edad_horas'])

        pendientes = (
            FacturaSRI.objects
            .filter(estado=FacturaSRI.EMITIDA, creada_en__gte=edad_limite)
            .exclude(clave_acceso__isnull=True).exclude(clave_acceso='')
            .order_by('creada_en')[:opts['limit']]
        )

        total = pendientes.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Sin facturas pendientes que reintentar.'))
            return

        self.stdout.write(f'Procesando {total} factura{"s" if total != 1 else ""}...')

        autorizadas = 0
        rechazadas = 0
        siguen_pendientes = 0
        errores = 0

        for f in pendientes:
            etiqueta = f'#{f.pk} ({f.numero_factura})'
            if opts['dry_run']:
                self.stdout.write(f'  [DRY-RUN] {etiqueta} — se consultaría al SRI')
                continue

            try:
                aut = consultar_autorizacion(f.clave_acceso, cfg.ambiente)
            except Exception as e:
                errores += 1
                self.stderr.write(self.style.WARNING(f'  ✗ {etiqueta}: error de conexión ({e})'))
                continue

            if aut['contingencia']:
                siguen_pendientes += 1
                self.stdout.write(f'  ⏳ {etiqueta}: SRI no disponible — sigue pendiente')
                continue

            if aut['estado'] == 'AUTORIZADO':
                f.estado = FacturaSRI.AUTORIZADA
                f.es_contingencia = False
                f.sri_numero_autorizacion = aut.get('numeroAutorizacion', '')
                from django.utils.dateparse import parse_datetime
                fa = aut.get('fechaAutorizacion')
                if fa:
                    parsed = parse_datetime(str(fa).replace(' ', 'T')) if fa else None
                    if parsed:
                        f.sri_fecha_autorizacion = parsed
                f.sri_respuesta = 'AUTORIZADA por reintento automático.'
                f.save()
                autorizadas += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ {etiqueta}: AUTORIZADA'))
            elif aut['estado'] in ('NO_AUTORIZADO', 'RECHAZADO'):
                err_msg = ' | '.join(
                    f'[{m.get("tipo","")}]{m.get("identificador","")}: {m.get("mensaje","")}'
                    for m in (aut.get('mensajes') or [])
                ) or 'No autorizada por SRI.'
                f.estado = FacturaSRI.RECHAZADA
                f.sri_respuesta = err_msg
                f.save(update_fields=['estado', 'sri_respuesta'])
                rechazadas += 1
                self.stdout.write(self.style.WARNING(f'  ✗ {etiqueta}: RECHAZADA — {err_msg[:80]}'))
            else:
                siguen_pendientes += 1
                self.stdout.write(f'  ⏳ {etiqueta}: estado SRI "{aut["estado"]}" — sigue pendiente')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Resumen: {autorizadas} autorizada(s), {rechazadas} rechazada(s), '
            f'{siguen_pendientes} pendiente(s), {errores} error(es)'
        ))
