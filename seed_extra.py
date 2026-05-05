"""
Seed adicional — agrega 3 adelantos, 3 deudas y 3 ventas más al contado.
NO toca empleados, clientes existentes ni inventario maestro.
Ejecutar: python seed_extra.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone

from apps.usuarios.models import Usuario
from apps.clientes.models import Cliente
from apps.inventario.models import Producto
from apps.ventas.models import Venta, ItemVenta
from apps.deudores.models import Adelanto, AdelantoItem, Deuda, Pago

print('=' * 50)
print('SEED EXTRA — adelantos + deudas + ventas')
print('=' * 50)

admin    = Usuario.objects.filter(rol='dueno').first() or Usuario.objects.first()
vendedor = Usuario.objects.filter(rol='vendedor').first() or admin

clientes = list(Cliente.objects.filter(activo=True).order_by('id'))
if len(clientes) < 3:
    print('Se necesitan al menos 3 clientes. Ejecuta seed_min.py primero.')
    sys.exit(1)

variantes = list(Producto.objects.filter(activo=True).order_by('id'))
if len(variantes) < 6:
    print('Se necesitan al menos 6 variantes. Ejecuta seed_min.py primero.')
    sys.exit(1)

# Mapeo rápido (basado en seed_min.py — 9 variantes en este orden)
camiseta_blanca = variantes[0]   # Camiseta Blanco M
camiseta_negra  = variantes[1]   # Camiseta Negro M
camiseta_gris   = variantes[2]   # Camiseta Gris L
jeans_30        = variantes[3]   # Jeans 30
jeans_32        = variantes[4]   # Jeans 32
jeans_negro     = variantes[5]   # Jeans Negro 32
vestido_coral   = variantes[6]   # Vestido Coral S
vestido_verde   = variantes[7]   # Vestido Verde M
vestido_amarillo = variantes[8]  # Vestido Amarillo S

hoy = date.today()


# ── 3 VENTAS AL CONTADO ADICIONALES ──────────────────────
ventas_data = [
    dict(cliente=clientes[0], dias=8,
         items=[dict(p=jeans_30, q=1, pu=Decimal('45.00'))]),
    dict(cliente=clientes[1], dias=6,
         items=[dict(p=camiseta_gris, q=2, pu=Decimal('12.00')),
                dict(p=vestido_amarillo, q=1, pu=Decimal('38.00'))]),
    dict(cliente=clientes[2], dias=2,
         items=[dict(p=jeans_negro, q=1, pu=Decimal('47.00'))]),
]
for v in ventas_data:
    total = sum(i['q'] * i['pu'] for i in v['items'])
    venta = Venta.objects.create(
        cliente=v['cliente'], tipo_pago='contado',
        total=total, vendedor=vendedor,
        fecha=timezone.now() - timedelta(days=v['dias']),
    )
    for i in v['items']:
        ItemVenta.objects.create(venta=venta, producto=i['p'],
                                 cantidad=i['q'], precio_unitario=i['pu'])
        i['p'].stock = max(0, i['p'].stock - i['q'])
        i['p'].save(update_fields=['stock'])
    print(f'  Venta #{venta.pk} contado — {venta.cliente.nombre} — ${venta.total}')
print(f'OK: {len(ventas_data)} ventas al contado')

# ── 3 ADELANTOS (apartados) ──────────────────────────────
adelantos_data = [
    dict(cliente=clientes[0], dias_limite=15, abono=Decimal('30.00'),
         notas='Aparta blusa para regalo',
         items=[dict(p=camiseta_blanca, q=1, pu=Decimal('12.00')),
                dict(p=jeans_32, q=1, pu=Decimal('45.00'))]),
    dict(cliente=clientes[1], dias_limite=20, abono=Decimal('20.00'),
         notas='Vestido para evento',
         items=[dict(p=vestido_verde, q=1, pu=Decimal('38.00'))]),
    dict(cliente=clientes[2], dias_limite=10, abono=Decimal('15.00'),
         notas='Pantalon talla especial',
         items=[dict(p=jeans_negro, q=1, pu=Decimal('47.00'))]),
]
for a in adelantos_data:
    total = sum(i['q'] * i['pu'] for i in a['items'])
    saldo = total - a['abono']
    adelanto = Adelanto.objects.create(
        cliente=a['cliente'], total=total, saldo_pendiente=saldo,
        estado=Adelanto.ACTIVO,
        fecha_limite=hoy + timedelta(days=a['dias_limite']),
        vendedor=vendedor, notas=a['notas'],
    )
    for i in a['items']:
        AdelantoItem.objects.create(adelanto=adelanto, producto=i['p'],
                                    cantidad=i['q'], precio_unitario=i['pu'])
        i['p'].stock_reservado += i['q']
        i['p'].save(update_fields=['stock_reservado'])
    Pago.objects.create(tipo='adelanto', referencia_id=adelanto.pk,
                        monto=a['abono'], forma_pago='efectivo', vendedor=vendedor)
    print(f'  Adelanto #{adelanto.pk} — {adelanto.cliente.nombre} — total ${total} / saldo ${saldo}')
print(f'OK: {len(adelantos_data)} adelantos')

# ── 3 DEUDAS (ventas a crédito) ──────────────────────────
deudas_data = [
    dict(cliente=clientes[0], dias_venta=12, dias_venc=18, abono=Decimal('20.00'),
         items=[dict(p=camiseta_negra, q=2, pu=Decimal('12.00')),
                dict(p=jeans_30, q=1, pu=Decimal('45.00'))]),
    dict(cliente=clientes[1], dias_venta=7, dias_venc=23, abono=Decimal('0.00'),
         items=[dict(p=vestido_coral, q=1, pu=Decimal('38.00'))]),
    dict(cliente=clientes[2], dias_venta=3, dias_venc=27, abono=Decimal('25.00'),
         items=[dict(p=camiseta_blanca, q=3, pu=Decimal('12.00')),
                dict(p=vestido_amarillo, q=1, pu=Decimal('38.00'))]),
]
for d in deudas_data:
    total = sum(i['q'] * i['pu'] for i in d['items'])
    venta = Venta.objects.create(
        cliente=d['cliente'], tipo_pago='credito',
        total=total, vendedor=vendedor,
        fecha=timezone.now() - timedelta(days=d['dias_venta']),
    )
    for i in d['items']:
        ItemVenta.objects.create(venta=venta, producto=i['p'],
                                 cantidad=i['q'], precio_unitario=i['pu'])
        i['p'].stock = max(0, i['p'].stock - i['q'])
        i['p'].save(update_fields=['stock'])

    saldo = total - d['abono']
    deuda = Deuda.objects.create(
        cliente=d['cliente'], venta=venta,
        monto_original=total, saldo_pendiente=saldo,
        estado=Deuda.PENDIENTE, vendedor=vendedor,
        fecha_vencimiento=hoy + timedelta(days=d['dias_venc']),
    )
    if d['abono'] > 0:
        Pago.objects.create(tipo='deuda', referencia_id=deuda.pk,
                            monto=d['abono'], forma_pago='efectivo', vendedor=vendedor)
    print(f'  Deuda #{deuda.pk} — {deuda.cliente.nombre} — ${total} / saldo ${saldo}')
print(f'OK: {len(deudas_data)} deudas')

# ── RESUMEN ──────────────────────────────────────────────
print('\n' + '=' * 50)
print('SEED EXTRA COMPLETADO')
print('=' * 50)
print(f'  Ventas (total)    : {Venta.objects.count()}')
print(f'  Adelantos activos : {Adelanto.objects.filter(estado=Adelanto.ACTIVO).count()}')
print(f'  Deudas pendientes : {Deuda.objects.filter(estado=Deuda.PENDIENTE).count()}')
print(f'  Pagos registrados : {Pago.objects.count()}')
print('=' * 50)
