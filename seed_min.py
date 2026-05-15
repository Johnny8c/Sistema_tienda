"""
Seed minimalista — pobla con 3 elementos por módulo.
NO toca empleados. NO crea adelantos ni deudas.
Ejecutar: python seed_min.py
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
from apps.inventario.models import CatalogoProducto, Producto, Categoria
from apps.proveedores.models import Proveedor, Compra, ItemCompra
from apps.ventas.models import Venta, ItemVenta

print('=' * 50)
print('SEED MINIMALISTA — 3 elementos por modulo')
print('=' * 50)

# Necesitamos un usuario para registrar (el admin o cualquier dueño)
admin = Usuario.objects.filter(rol='dueno').first()
if not admin:
    admin = Usuario.objects.first()

# Vendedor para asignar a las ventas (si existe, sino usa admin)
vendedor = Usuario.objects.filter(rol='vendedor').first() or admin

# ── CLIENTES ─────────────────────────────────────────────
clientes_data = [
    dict(nombre='Maria Jose Rodriguez', cedula_ruc='1712345678',
         telefono='0991234567', email='maria@gmail.com',
         direccion='Av. 9 de Octubre, Guayaquil'),
    dict(nombre='Carlos Andres Pena', cedula_ruc='1723456789',
         telefono='0987654321', email='carlos@gmail.com',
         direccion='Calle Sucre, Quito'),
    dict(nombre='Sofia Valentina Cruz', cedula_ruc='1734567890',
         telefono='0976543210', email='sofia@gmail.com',
         direccion='Av. Amazonas, Quito'),
]
clientes = []
for c in clientes_data:
    obj, _ = Cliente.objects.get_or_create(cedula_ruc=c['cedula_ruc'], defaults=c)
    clientes.append(obj)
    print(f'  Cliente: {obj.nombre}')
print(f'OK: {len(clientes)} clientes')

# ── PROVEEDORES ──────────────────────────────────────────
proveedores_data = [
    dict(nombre='Textiles del Ecuador SA', ruc='1790012345001',
         telefono='022345678', email='ventas@textilesec.com',
         contacto='Roberto Salinas'),
    dict(nombre='Confecciones Quito Ltda', ruc='1790098765001',
         telefono='022987654', email='pedidos@confecciones.com',
         contacto='Carmen Rios'),
    dict(nombre='Modas Internacional', ruc='0990123456001',
         telefono='042123456', email='info@modasint.com',
         contacto='Miguel Espinoza'),
]
proveedores = []
for p in proveedores_data:
    obj, _ = Proveedor.objects.get_or_create(ruc=p['ruc'], defaults=p)
    proveedores.append(obj)
    print(f'  Proveedor: {obj.nombre}')
print(f'OK: {len(proveedores)} proveedores')

# ── CATALOGO DE PRODUCTOS (3 productos x 3 variantes = 9) ──
catalogo_data = [
    dict(
        nombre='Camiseta Basica Algodon', categoria='camisetas',
        precio_base=Decimal('12.00'),
        descripcion='Camiseta 100% algodon, corte regular.',
        variantes=[
            dict(color='Blanco', talla='M', precio=Decimal('12.00'), stock=20),
            dict(color='Negro',  talla='M', precio=Decimal('12.00'), stock=15),
            dict(color='Gris',   talla='L', precio=Decimal('12.00'), stock=10),
        ]
    ),
    dict(
        nombre='Jeans Slim Fit', categoria='pantalones',
        precio_base=Decimal('45.00'),
        descripcion='Jean de corte slim, denim 98% algodon.',
        variantes=[
            dict(color='Azul Oscuro', talla='30', precio=Decimal('45.00'), stock=8),
            dict(color='Azul Oscuro', talla='32', precio=Decimal('45.00'), stock=12),
            dict(color='Negro',       talla='32', precio=Decimal('47.00'), stock=10),
        ]
    ),
    dict(
        nombre='Vestido Casual Verano', categoria='vestidos',
        precio_base=Decimal('38.00'),
        descripcion='Vestido ligero para uso diario.',
        variantes=[
            dict(color='Coral',       talla='S', precio=Decimal('38.00'), stock=6),
            dict(color='Verde Menta', talla='M', precio=Decimal('38.00'), stock=8),
            dict(color='Amarillo',    talla='S', precio=Decimal('38.00'), stock=5),
        ]
    ),
]
variantes = []
for c in catalogo_data:
    cat_obj, _ = Categoria.objects.get_or_create(nombre=c['categoria'].title())
    cat, _ = CatalogoProducto.objects.get_or_create(nombre=c['nombre'], defaults={
        'categoria':   cat_obj,
        'precio_base': c['precio_base'],
        'descripcion': c['descripcion'],
    })
    for v in c['variantes']:
        var = Producto.objects.create(
            catalogo=cat, nombre=cat.nombre,
            color=v['color'], talla=v['talla'],
            precio=v['precio'], stock=v['stock'],
        )
        var.codigo_barras = f'TDA-{var.id:06d}'
        var.save(update_fields=['codigo_barras'])
        variantes.append(var)
    print(f'  Catalogo: {cat.nombre} ({len(c["variantes"])} variantes)')
print(f'OK: {len(catalogo_data)} catalogos, {len(variantes)} variantes')

# Referencias rapidas
camiseta_blanca = variantes[0]
camiseta_negra  = variantes[1]
jeans_32        = variantes[4]
vestido_coral   = variantes[6]
vestido_verde   = variantes[7]

# ── COMPRAS (3) ──────────────────────────────────────────
hoy = date.today()
compras_data = [
    dict(proveedor=proveedores[0], fecha=hoy - timedelta(days=20),
         factura='F-001-0001100', estado='pagada',
         notas='Reposicion camisetas',
         items=[
             dict(p=camiseta_blanca, q=15, pu=Decimal('7.00')),
             dict(p=camiseta_negra,  q=15, pu=Decimal('7.00')),
         ]),
    dict(proveedor=proveedores[1], fecha=hoy - timedelta(days=10),
         factura='F-002-0003456', estado='pagada',
         notas='Pantalones temporada',
         items=[
             dict(p=jeans_32, q=10, pu=Decimal('28.00')),
         ]),
    dict(proveedor=proveedores[2], fecha=hoy - timedelta(days=3),
         factura='F-003-0001122', estado='pendiente',
         notas='Vestidos nueva coleccion',
         items=[
             dict(p=vestido_coral, q=8, pu=Decimal('22.00')),
             dict(p=vestido_verde, q=8, pu=Decimal('22.00')),
         ]),
]
for c in compras_data:
    total = sum(i['q'] * i['pu'] for i in c['items'])
    compra = Compra.objects.create(
        proveedor=c['proveedor'], fecha=c['fecha'],
        numero_factura=c['factura'], estado=c['estado'],
        notas=c['notas'], total=total, registrado_por=admin,
    )
    for i in c['items']:
        ItemCompra.objects.create(
            compra=compra, producto=i['p'],
            cantidad=i['q'], precio_unitario=i['pu'],
        )
    print(f'  Compra #{compra.pk} — {compra.proveedor} — ${compra.total}')
print(f'OK: {len(compras_data)} compras')

# ── VENTAS (3 al contado) ────────────────────────────────
ventas_data = [
    dict(cliente=clientes[0], dias=5,
         items=[
             dict(p=camiseta_blanca, q=2, pu=Decimal('12.00')),
             dict(p=jeans_32,        q=1, pu=Decimal('45.00')),
         ]),
    dict(cliente=clientes[1], dias=3,
         items=[
             dict(p=vestido_coral, q=1, pu=Decimal('38.00')),
         ]),
    dict(cliente=clientes[2], dias=1,
         items=[
             dict(p=camiseta_negra, q=3, pu=Decimal('12.00')),
             dict(p=vestido_verde,  q=1, pu=Decimal('38.00')),
         ]),
]
for v in ventas_data:
    total = sum(i['q'] * i['pu'] for i in v['items'])
    venta = Venta.objects.create(
        cliente=v['cliente'], tipo_pago='contado',
        total=total, vendedor=vendedor,
        fecha=timezone.now() - timedelta(days=v['dias']),
    )
    for i in v['items']:
        ItemVenta.objects.create(
            venta=venta, producto=i['p'],
            cantidad=i['q'], precio_unitario=i['pu'],
        )
        i['p'].stock = max(0, i['p'].stock - i['q'])
        i['p'].save(update_fields=['stock'])
    print(f'  Venta #{venta.pk} — {venta.cliente.nombre} — ${venta.total}')
print(f'OK: {len(ventas_data)} ventas al contado')

# ── RESUMEN ──────────────────────────────────────────────
print('\n' + '=' * 50)
print('SEED COMPLETADO')
print('=' * 50)
print(f'  Empleados (no tocados): {Usuario.objects.count()}')
print(f'  Clientes               : {Cliente.objects.count()}')
print(f'  Catalogos              : {CatalogoProducto.objects.count()}')
print(f'  Variantes              : {Producto.objects.count()}')
print(f'  Proveedores            : {Proveedor.objects.count()}')
print(f'  Compras                : {Compra.objects.count()}')
print(f'  Ventas                 : {Venta.objects.count()}')
print('=' * 50)
