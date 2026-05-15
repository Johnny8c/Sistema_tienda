"""
Script de seed — ejecutar con: python seed.py
Inserta datos de prueba realistas para una tienda de ropa en Ecuador.
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

# ── USUARIOS ─────────────────────────────────────────────
from apps.usuarios.models import Usuario

empleados = [
    dict(username='ana.garcia',   password='tienda2024', first_name='Ana',    last_name='Garcia',   rol='vendedor'),
    dict(username='carlos.lopez', password='tienda2024', first_name='Carlos', last_name='Lopez',    rol='vendedor'),
    dict(username='maria.torres', password='tienda2024', first_name='Maria',  last_name='Torres',   rol='bodeguero'),
    dict(username='pedro.mora',   password='tienda2024', first_name='Pedro',  last_name='Mora',     rol='vendedor'),
    dict(username='lucia.vega',   password='tienda2024', first_name='Lucia',  last_name='Vega',     rol='bodeguero'),
]
usuarios_creados = {}
for e in empleados:
    u, _ = Usuario.objects.get_or_create(username=e['username'], defaults={
        'first_name': e['first_name'], 'last_name': e['last_name'], 'rol': e['rol'],
    })
    u.set_password(e['password'])
    u.save()
    usuarios_creados[e['username']] = u
    print(f'  Usuario: {u.get_full_name()} ({u.get_rol_display()})')

admin    = Usuario.objects.get(username='admin')
vendedor1 = usuarios_creados['ana.garcia']
vendedor2 = usuarios_creados['carlos.lopez']
print(f'OK: {len(empleados)} empleados creados')

# ── CLIENTES ─────────────────────────────────────────────
from apps.clientes.models import Cliente

clientes_data = [
    dict(nombre='Maria Jose Rodriguez', cedula_ruc='1712345678',  telefono='0991234567', email='maria.rodriguez@gmail.com',  direccion='Av. 9 de Octubre 123, Guayaquil'),
    dict(nombre='Carlos Andres Pena',   cedula_ruc='1723456789',  telefono='0987654321', email='carlos.pena@hotmail.com',    direccion='Calle Sucre 456, Quito'),
    dict(nombre='Sofia Valentina Cruz', cedula_ruc='1734567890',  telefono='0976543210', email='sofia.cruz@gmail.com',       direccion='Av. Amazonas 789, Quito'),
    dict(nombre='Diego Alejandro Mora', cedula_ruc='1745678901',  telefono='0965432109', email='diego.mora@outlook.com',     direccion='Calle Bolivar 321, Cuenca'),
    dict(nombre='Patricia Elena Vega',  cedula_ruc='1756789012',  telefono='0954321098', email='patricia.vega@gmail.com',    direccion='Av. 6 de Diciembre 654, Quito'),
    dict(nombre='Luis Fernando Ortiz',  cedula_ruc='1767890123',  telefono='0943210987', email='luis.ortiz@hotmail.com',     direccion='Cdla. Kennedy Norte, Guayaquil'),
    dict(nombre='Ana Lucia Zambrano',   cedula_ruc='1778901234',  telefono='0932109876', email='ana.zambrano@gmail.com',     direccion='Av. Colon 987, Quito'),
]
clientes_creados = []
for c in clientes_data:
    obj, _ = Cliente.objects.get_or_create(cedula_ruc=c['cedula_ruc'], defaults=c)
    clientes_creados.append(obj)
    print(f'  Cliente: {obj.nombre}')
print(f'OK: {len(clientes_creados)} clientes creados')

# ── CATALOGO + VARIANTES ──────────────────────────────────
from apps.inventario.models import CatalogoProducto, Producto, Categoria

# Categorías de ejemplo
CATEGORIAS_LABELS = {
    'blusas': 'Blusas', 'camisas': 'Camisas', 'camisetas': 'Camisetas',
    'pantalones': 'Pantalones', 'vestidos': 'Vestidos', 'chaquetas': 'Chaquetas',
}
_cat_cache = {}
def _categoria(slug):
    if slug not in _cat_cache:
        _cat_cache[slug], _ = Categoria.objects.get_or_create(nombre=CATEGORIAS_LABELS.get(slug, slug.title()))
    return _cat_cache[slug]

catalogo_data = [
    dict(
        nombre='Blusa Floral Manga Corta', categoria='blusas',
        precio_base=Decimal('24.99'), descripcion='Blusa con estampado floral, tela chifon.',
        variantes=[
            dict(color='Blanco',  talla='S',  precio=Decimal('24.99'), stock=15),
            dict(color='Blanco',  talla='M',  precio=Decimal('24.99'), stock=20),
            dict(color='Rosado',  talla='M',  precio=Decimal('24.99'), stock=12),
            dict(color='Rosado',  talla='L',  precio=Decimal('24.99'), stock=8),
            dict(color='Celeste', talla='S',  precio=Decimal('24.99'), stock=10),
        ]
    ),
    dict(
        nombre='Jeans Slim Fit', categoria='pantalones',
        precio_base=Decimal('45.00'), descripcion='Jean de corte slim, tela denim 98% algodon.',
        variantes=[
            dict(color='Azul Oscuro', talla='30', precio=Decimal('45.00'), stock=10),
            dict(color='Azul Oscuro', talla='32', precio=Decimal('45.00'), stock=18),
            dict(color='Azul Oscuro', talla='34', precio=Decimal('45.00'), stock=12),
            dict(color='Negro',       talla='30', precio=Decimal('47.00'), stock=8),
            dict(color='Negro',       talla='32', precio=Decimal('47.00'), stock=14),
        ]
    ),
    dict(
        nombre='Camisa Oxford Clasica', categoria='camisas',
        precio_base=Decimal('32.50'), descripcion='Camisa formal de tela oxford, ideal para oficina.',
        variantes=[
            dict(color='Blanco',  talla='S',  precio=Decimal('32.50'), stock=12),
            dict(color='Blanco',  talla='M',  precio=Decimal('32.50'), stock=20),
            dict(color='Blanco',  talla='L',  precio=Decimal('32.50'), stock=15),
            dict(color='Celeste', talla='M',  precio=Decimal('32.50'), stock=10),
            dict(color='Celeste', talla='L',  precio=Decimal('32.50'), stock=8),
        ]
    ),
    dict(
        nombre='Vestido Casual Verano', categoria='vestidos',
        precio_base=Decimal('38.00'), descripcion='Vestido ligero para el dia a dia, con bolsillos.',
        variantes=[
            dict(color='Verde Menta', talla='S',  precio=Decimal('38.00'), stock=7),
            dict(color='Verde Menta', talla='M',  precio=Decimal('38.00'), stock=11),
            dict(color='Coral',       talla='M',  precio=Decimal('38.00'), stock=9),
            dict(color='Coral',       talla='L',  precio=Decimal('38.00'), stock=6),
            dict(color='Amarillo',    talla='S',  precio=Decimal('38.00'), stock=5),
        ]
    ),
    dict(
        nombre='Chaqueta Denim', categoria='chaquetas',
        precio_base=Decimal('55.00'), descripcion='Chaqueta de mezclilla clasica, unisex.',
        variantes=[
            dict(color='Azul Desgastado', talla='S',  precio=Decimal('55.00'), stock=6),
            dict(color='Azul Desgastado', talla='M',  precio=Decimal('55.00'), stock=10),
            dict(color='Azul Desgastado', talla='L',  precio=Decimal('55.00'), stock=8),
            dict(color='Negro',           talla='M',  precio=Decimal('58.00'), stock=7),
            dict(color='Negro',           talla='L',  precio=Decimal('58.00'), stock=5),
        ]
    ),
    dict(
        nombre='Camiseta Basica Algodon', categoria='camisetas',
        precio_base=Decimal('12.00'), descripcion='Camiseta 100% algodon, corte regular.',
        variantes=[
            dict(color='Blanco',  talla='S',  precio=Decimal('12.00'), stock=30),
            dict(color='Blanco',  talla='M',  precio=Decimal('12.00'), stock=40),
            dict(color='Negro',   talla='S',  precio=Decimal('12.00'), stock=25),
            dict(color='Negro',   talla='M',  precio=Decimal('12.00'), stock=35),
            dict(color='Gris',    talla='L',  precio=Decimal('12.00'), stock=20),
        ]
    ),
    dict(
        nombre='Pantalon Chino Slim', categoria='pantalones',
        precio_base=Decimal('40.00'), descripcion='Pantalon chino de gabardina, estilo casual-formal.',
        variantes=[
            dict(color='Beige',  talla='30', precio=Decimal('40.00'), stock=10),
            dict(color='Beige',  talla='32', precio=Decimal('40.00'), stock=14),
            dict(color='Cafe',   talla='30', precio=Decimal('40.00'), stock=8),
            dict(color='Cafe',   talla='32', precio=Decimal('40.00'), stock=12),
            dict(color='Verde',  talla='34', precio=Decimal('42.00'), stock=6),
        ]
    ),
]

catalogos_creados = []
variantes_creadas = []
for c in catalogo_data:
    cat, _ = CatalogoProducto.objects.get_or_create(nombre=c['nombre'], defaults={
        'categoria': _categoria(c['categoria']),
        'precio_base': c['precio_base'],
        'descripcion': c['descripcion'],
    })
    catalogos_creados.append(cat)
    for v in c['variantes']:
        var = Producto.objects.create(
            catalogo=cat, nombre=cat.nombre,
            color=v['color'], talla=v['talla'],
            precio=v['precio'], stock=v['stock'],
        )
        var.codigo_barras = f'TDA-{var.id:06d}'
        var.save(update_fields=['codigo_barras'])
        variantes_creadas.append(var)
    print(f'  Catalogo: {cat.nombre} ({len(c["variantes"])} variantes)')

print(f'OK: {len(catalogos_creados)} catalogos, {len(variantes_creadas)} variantes')

# Referencias para ventas/compras
def variante(nombre_cat, color, talla):
    return Producto.objects.filter(catalogo__nombre=nombre_cat, color=color, talla=talla).first()

blusa_s    = variante('Blusa Floral Manga Corta',  'Blanco',        'S')
blusa_m    = variante('Blusa Floral Manga Corta',  'Rosado',        'M')
jeans_32   = variante('Jeans Slim Fit',            'Azul Oscuro',   '32')
jeans_30   = variante('Jeans Slim Fit',            'Negro',         '30')
camisa_m   = variante('Camisa Oxford Clasica',     'Blanco',        'M')
camisa_l   = variante('Camisa Oxford Clasica',     'Celeste',       'L')
vestido_m  = variante('Vestido Casual Verano',     'Verde Menta',   'M')
vestido_c  = variante('Vestido Casual Verano',     'Coral',         'M')
chaqueta_m = variante('Chaqueta Denim',            'Azul Desgastado', 'M')
chaqueta_n = variante('Chaqueta Denim',            'Negro',         'L')
camiseta_m = variante('Camiseta Basica Algodon',   'Blanco',        'M')
camiseta_n = variante('Camiseta Basica Algodon',   'Negro',         'M')
pantalon_32 = variante('Pantalon Chino Slim',      'Beige',         '32')
pantalon_c  = variante('Pantalon Chino Slim',      'Cafe',          '32')

# ── PROVEEDORES ───────────────────────────────────────────
from apps.proveedores.models import Proveedor, Compra, ItemCompra

proveedores_data = [
    dict(nombre='Textiles del Ecuador SA',       ruc='1790012345001', telefono='022345678', email='ventas@textilesec.com',        contacto='Roberto Salinas'),
    dict(nombre='Confecciones Quito Ltda',       ruc='1790098765001', telefono='022987654', email='pedidos@confeccionesquito.com', contacto='Carmen Rios'),
    dict(nombre='Importadora Modas Guayaquil',   ruc='0990123456001', telefono='042123456', email='info@modasgye.com',             contacto='Miguel Espinoza'),
    dict(nombre='Disenos y Telas Cuenca',        ruc='0190234567001', telefono='072234567', email='ventas@telascuenca.com',        contacto='Isabel Crespo'),
    dict(nombre='Fashion Supply International',  ruc='1791345678001', telefono='022456789', email='orders@fashionsupply.ec',      contacto='Andres Villacis'),
]
proveedores_creados = []
for p in proveedores_data:
    obj, _ = Proveedor.objects.get_or_create(ruc=p['ruc'], defaults=p)
    proveedores_creados.append(obj)
    print(f'  Proveedor: {obj.nombre}')
print(f'OK: {len(proveedores_creados)} proveedores creados')

# ── COMPRAS ───────────────────────────────────────────────
hoy = date.today()

compras_data = [
    dict(proveedor=proveedores_creados[0], fecha=hoy-timedelta(days=45), factura='F-001-0001100', estado='pagada',   notas='Pedido inicial apertura',
         items=[dict(p=camisa_m, q=40, pu=Decimal('19.50')), dict(p=pantalon_32, q=30, pu=Decimal('23.00'))]),
    dict(proveedor=proveedores_creados[0], fecha=hoy-timedelta(days=30), factura='F-001-0001245', estado='pagada',   notas='Reposicion blusas y camisetas',
         items=[dict(p=blusa_s, q=30, pu=Decimal('15.00')), dict(p=camiseta_m, q=50, pu=Decimal('7.00'))]),
    dict(proveedor=proveedores_creados[1], fecha=hoy-timedelta(days=22), factura='F-002-0003456', estado='pagada',   notas='Pantalones temporada',
         items=[dict(p=jeans_32, q=25, pu=Decimal('28.00')), dict(p=pantalon_c, q=20, pu=Decimal('24.00'))]),
    dict(proveedor=proveedores_creados[2], fecha=hoy-timedelta(days=15), factura='F-001-0007890', estado='pagada',   notas='Camisas formales',
         items=[dict(p=camisa_m, q=30, pu=Decimal('20.00')), dict(p=camisa_l, q=20, pu=Decimal('20.00'))]),
    dict(proveedor=proveedores_creados[3], fecha=hoy-timedelta(days=8),  factura='F-003-0001122', estado='pendiente', notas='Vestidos y chaquetas nueva coleccion',
         items=[dict(p=vestido_m, q=20, pu=Decimal('22.00')), dict(p=chaqueta_m, q=15, pu=Decimal('34.00'))]),
    dict(proveedor=proveedores_creados[4], fecha=hoy-timedelta(days=3),  factura='FS-2024-0089',  estado='pendiente', notas='Reposicion stock general',
         items=[dict(p=blusa_m, q=20, pu=Decimal('14.50')), dict(p=jeans_30, q=15, pu=Decimal('27.00')), dict(p=camiseta_n, q=40, pu=Decimal('6.50'))]),
]

for c in compras_data:
    total = sum(i['q'] * i['pu'] for i in c['items'])
    compra = Compra.objects.create(
        proveedor=c['proveedor'], fecha=c['fecha'], numero_factura=c['factura'],
        estado=c['estado'], notas=c['notas'], total=total, registrado_por=admin,
    )
    for i in c['items']:
        ItemCompra.objects.create(compra=compra, producto=i['p'], cantidad=i['q'], precio_unitario=i['pu'])
    print(f'  Compra #{compra.pk} — {compra.proveedor} — ${compra.total}')
print(f'OK: {len(compras_data)} compras registradas')

# ── VENTAS AL CONTADO ─────────────────────────────────────
from apps.ventas.models import Venta, ItemVenta

def crear_venta(cliente, vendedor, tipo, dias_atras, items):
    total = sum(i['q'] * i['pu'] for i in items)
    v = Venta.objects.create(
        cliente=cliente, tipo_pago=tipo, total=total, vendedor=vendedor,
        fecha=timezone.now() - timedelta(days=dias_atras),
    )
    for i in items:
        ItemVenta.objects.create(venta=v, producto=i['p'], cantidad=i['q'], precio_unitario=i['pu'])
        i['p'].stock = max(0, i['p'].stock - i['q'])
        i['p'].save(update_fields=['stock'])
    return v

ventas = [
    crear_venta(clientes_creados[0], vendedor1, 'contado', 25,
                [dict(p=blusa_s, q=2, pu=Decimal('24.99')), dict(p=camiseta_m, q=3, pu=Decimal('12.00'))]),
    crear_venta(clientes_creados[1], vendedor2, 'contado', 20,
                [dict(p=jeans_32, q=1, pu=Decimal('45.00')), dict(p=camisa_m, q=2, pu=Decimal('32.50'))]),
    crear_venta(clientes_creados[2], vendedor1, 'contado', 18,
                [dict(p=vestido_c, q=1, pu=Decimal('38.00'))]),
    crear_venta(clientes_creados[3], vendedor2, 'contado', 14,
                [dict(p=chaqueta_n, q=1, pu=Decimal('58.00')), dict(p=pantalon_32, q=1, pu=Decimal('40.00'))]),
    crear_venta(clientes_creados[4], vendedor1, 'contado', 10,
                [dict(p=camiseta_m, q=5, pu=Decimal('12.00')), dict(p=blusa_s, q=2, pu=Decimal('24.99'))]),
    crear_venta(clientes_creados[5], vendedor2, 'contado', 7,
                [dict(p=camisa_l, q=3, pu=Decimal('32.50'))]),
    crear_venta(clientes_creados[6], vendedor1, 'contado', 2,
                [dict(p=jeans_30, q=2, pu=Decimal('47.00')), dict(p=camiseta_n, q=4, pu=Decimal('12.00'))]),
]
for v in ventas:
    print(f'  Venta #{v.pk} contado — {v.cliente} — ${v.total}')
print(f'OK: {len(ventas)} ventas al contado')

# ── ADELANTOS ─────────────────────────────────────────────
from apps.deudores.models import Adelanto, AdelantoItem, Deuda, Pago

adelantos_data = [
    dict(cliente=clientes_creados[0], vendedor=vendedor1, limite=hoy+timedelta(days=15), abono=Decimal('30.00'),
         notas='Aparta blusa y jeans para regalo',
         items=[dict(p=blusa_s, q=1, pu=Decimal('24.99')), dict(p=jeans_32, q=1, pu=Decimal('45.00'))]),
    dict(cliente=clientes_creados[1], vendedor=vendedor2, limite=hoy+timedelta(days=20), abono=Decimal('50.00'),
         notas='Conjunto de oficina',
         items=[dict(p=camisa_m, q=2, pu=Decimal('32.50')), dict(p=pantalon_32, q=1, pu=Decimal('40.00'))]),
    dict(cliente=clientes_creados[2], vendedor=vendedor1, limite=hoy+timedelta(days=30), abono=Decimal('20.00'),
         notas='Vestido para evento especial',
         items=[dict(p=vestido_m, q=1, pu=Decimal('38.00'))]),
    dict(cliente=clientes_creados[4], vendedor=vendedor2, limite=hoy+timedelta(days=10), abono=Decimal('25.00'),
         notas='Chaqueta temporada fria',
         items=[dict(p=chaqueta_m, q=1, pu=Decimal('55.00'))]),
    dict(cliente=clientes_creados[6], vendedor=vendedor1, limite=hoy+timedelta(days=25), abono=Decimal('20.00'),
         notas='Camisetas para trabajo',
         items=[dict(p=camiseta_m, q=4, pu=Decimal('12.00'))]),
]

for a in adelantos_data:
    total = sum(i['q'] * i['pu'] for i in a['items'])
    saldo = total - a['abono']
    adelanto = Adelanto.objects.create(
        cliente=a['cliente'], total=total, saldo_pendiente=saldo,
        estado='activo', fecha_limite=a['limite'],
        vendedor=a['vendedor'], notas=a['notas'],
    )
    for i in a['items']:
        AdelantoItem.objects.create(adelanto=adelanto, producto=i['p'], cantidad=i['q'], precio_unitario=i['pu'])
        i['p'].stock_reservado += i['q']
        i['p'].save(update_fields=['stock_reservado'])
    Pago.objects.create(tipo='adelanto', referencia_id=adelanto.pk, monto=a['abono'], forma_pago='efectivo', vendedor=a['vendedor'])
    print(f'  Adelanto #{adelanto.pk} — {adelanto.cliente} — total ${adelanto.total} / saldo ${adelanto.saldo_pendiente}')
print(f'OK: {len(adelantos_data)} adelantos registrados')

# ── DEUDAS (ventas a credito) ─────────────────────────────
deudas_data = [
    dict(cliente=clientes_creados[3], vendedor=vendedor2, dias=20, venc=10, abono=Decimal('40.00'),
         items=[dict(p=chaqueta_m, q=1, pu=Decimal('55.00')), dict(p=jeans_32, q=1, pu=Decimal('45.00'))]),
    dict(cliente=clientes_creados[5], vendedor=vendedor1, dias=15, venc=15, abono=Decimal('30.00'),
         items=[dict(p=vestido_c, q=2, pu=Decimal('38.00'))]),
    dict(cliente=clientes_creados[1], vendedor=vendedor2, dias=12, venc=18, abono=Decimal('0.00'),
         items=[dict(p=camisa_l, q=3, pu=Decimal('32.50'))]),
    dict(cliente=clientes_creados[4], vendedor=vendedor1, dias=8,  venc=22, abono=Decimal('50.00'),
         items=[dict(p=camiseta_n, q=6, pu=Decimal('12.00')), dict(p=blusa_m, q=2, pu=Decimal('24.99'))]),
    dict(cliente=clientes_creados[6], vendedor=vendedor2, dias=5,  venc=25, abono=Decimal('20.00'),
         items=[dict(p=pantalon_c, q=2, pu=Decimal('40.00'))]),
    dict(cliente=clientes_creados[0], vendedor=vendedor1, dias=3,  venc=27, abono=Decimal('0.00'),
         items=[dict(p=chaqueta_n, q=1, pu=Decimal('58.00'))]),
]

for d in deudas_data:
    venta = crear_venta(d['cliente'], d['vendedor'], 'credito', d['dias'], d['items'])
    total = venta.total
    saldo = total - d['abono']
    deuda = Deuda.objects.create(
        cliente=d['cliente'], venta=venta, monto_original=total, saldo_pendiente=saldo,
        estado='pendiente', vendedor=d['vendedor'],
        fecha_vencimiento=hoy + timedelta(days=d['venc']),
    )
    if d['abono'] > 0:
        Pago.objects.create(tipo='deuda', referencia_id=deuda.pk, monto=d['abono'], forma_pago='efectivo', vendedor=d['vendedor'])
    print(f'  Deuda #{deuda.pk} — {deuda.cliente} — ${deuda.monto_original} / saldo ${deuda.saldo_pendiente}')
print(f'OK: {len(deudas_data)} deudas registradas')

# ── RESUMEN ───────────────────────────────────────────────
from apps.proveedores.models import Compra
print('\n' + '='*50)
print('SEED COMPLETADO')
print('='*50)
print(f'  Empleados  : {Usuario.objects.exclude(username="admin").count()}')
print(f'  Clientes   : {Cliente.objects.count()}')
print(f'  Catalogos  : {CatalogoProducto.objects.count()}')
print(f'  Variantes  : {Producto.objects.count()}')
print(f'  Proveedores: {Proveedor.objects.count()}')
print(f'  Compras    : {Compra.objects.count()}')
print(f'  Ventas     : {Venta.objects.count()}')
print(f'  Adelantos  : {Adelanto.objects.count()}')
print(f'  Deudas     : {Deuda.objects.count()}')
print('='*50)
