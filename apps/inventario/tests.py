"""Pruebas del conteo de etiquetas frente al ingreso de mercadería.

Reproducen el reclamo real: "se ingresaron ~100 prendas entre categorías
nuevas, variantes nuevas y aumentos de stock, pero la pantalla de etiquetas
solo da 95". Cada escenario usa las vistas reales (test client) y al final
se replica en Python la misma lógica de conteo del JS de etiquetas.html
(fueImpresa / faltantesEtiqueta / getPendientes / contarEtiquetas) para
verificar cuántas etiquetas mostraría la pantalla.

Todos los datos llevan la marca "TEST" en el nombre.
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Categoria, CatalogoProducto, Producto, EtiquetaImpresa, MovimientoInventario

Usuario = get_user_model()

MARCA = 'TEST'


# ── Réplica exacta de la lógica de conteo del frontend (etiquetas.html) ──

def _fue_impresa(p, impresas):
    """Port de fueImpresa(): variante totalmente etiquetada."""
    if not p['codigo_barras']:
        return False
    info = impresas.get(p['codigo_barras'])
    if not info:
        return False
    if info['stock_al_imprimir'] is None:
        return True  # registro legacy: se trata como "todo impreso"
    return info['stock_al_imprimir'] >= (p['stock'] or 0)


def _faltantes(p, impresas):
    """Port de faltantesEtiqueta(): etiquetas que faltan para esa variante."""
    if not p['codigo_barras']:
        return 0
    stock = p['stock'] or 0
    info = impresas.get(p['codigo_barras'])
    if not info:
        return stock
    if info['stock_al_imprimir'] is None:
        return 0
    return max(0, stock - info['stock_al_imprimir'])


def _contar_etiquetas_pendientes(productos, impresas):
    """Port de getPendientes() + contarEtiquetas() en modo 'auto':
    lo que diría el botón 'Imprimir faltantes'."""
    pendientes = [p for p in productos
                  if p['codigo_barras'] and not _fue_impresa(p, impresas)]
    total = 0
    for p in pendientes:
        faltan = _faltantes(p, impresas)
        total += faltan if faltan > 0 else max(1, p['stock'] or 1)
    return pendientes, total


# Storage de estáticos simple para tests: el manifest de whitenoise exige
# collectstatic actualizado y rompe cualquier render de página completa con
# "Missing staticfiles manifest entry" en entornos sin él.
@override_settings(STORAGES={
    'default':     {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class EtiquetasIngresoMercaderiaTest(TestCase):
    """Simula el ingreso real del señor: ~100 prendas TEST entre categoría
    nueva, variantes nuevas y aumentos de stock. Verifica que la pantalla
    de etiquetas cuente las 100."""

    def setUp(self):
        self.user = Usuario.objects.create_user(
            username='test_bodeguero', password='x',
            rol=Usuario.ROL_DUENO,
        )
        self.client.force_login(self.user)

    # ── helpers que pasan por las vistas reales ──

    def _crear_categoria(self, nombre):
        r = self.client.post(reverse('crear_categoria'), {'nombre': nombre})
        self.assertEqual(r.status_code, 302, f'crear_categoria falló: {r.status_code}')
        return Categoria.objects.get(nombre=nombre)

    def _crear_producto(self, nombre, categoria, stock, talla='M', color='Negro'):
        r = self.client.post(reverse('crear_producto'), {
            'nombre': nombre,
            'categoria': categoria.pk if categoria else '',
            'precio_minimo': '10.00', 'precio_maximo': '15.00',
            'color': color, 'talla': talla, 'stock': str(stock),
        })
        self.assertEqual(r.status_code, 302, f'crear_producto falló: {r.status_code}')
        return CatalogoProducto.objects.get(nombre=nombre)

    def _agregar_variante(self, catalogo, stock, talla, color):
        r = self.client.post(reverse('agregar_variante', args=[catalogo.pk]), {
            'color': color, 'talla': talla, 'precio': '12.00', 'stock': str(stock),
        })
        self.assertEqual(r.status_code, 302, f'agregar_variante falló: {r.status_code}')
        return catalogo.variantes.get(talla=talla, color=color)

    def _ajustar_stock(self, variante, nuevo_stock):
        r = self.client.post(reverse('ajustar_stock', args=[variante.pk]),
                             {'stock': str(nuevo_stock)})
        self.assertEqual(r.status_code, 302, f'ajustar_stock falló: {r.status_code}')
        variante.refresh_from_db()

    def _marcar_impresas(self, variante, cantidad):
        """Simula que el usuario imprimió `cantidad` etiquetas de la variante
        (el POST que hace el navegador al confirmar la impresión)."""
        r = self.client.post(
            reverse('api_etiquetas_marcar'),
            data=json.dumps({'items': [
                {'codigo_barras': variante.codigo_barras, 'cantidad': cantidad},
            ]}),
            content_type='application/json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get('ok'))

    def _estado_etiquetas(self):
        """Lo que el frontend recibe (carga inicial / refresco automático),
        filtrado a los productos de esta prueba."""
        r = self.client.get(reverse('api_etiquetas_estado'))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        productos = [p for p in data['productos'] if MARCA in p['nombre']]
        return productos, data['impresas']

    # ── la prueba principal: 100 prendas ingresadas ──

    def test_ingreso_100_prendas_salen_100_etiquetas(self):
        # ESCENARIO 1 — Categoría nueva + producto nuevo con 3 variantes
        # (30 + 20 + 15 = 65 prendas)
        cat_nueva = self._crear_categoria(f'{MARCA} Categoría Nueva')
        prod_nuevo = self._crear_producto(f'{MARCA} Chompa Prueba', cat_nueva, stock=30)
        self._agregar_variante(prod_nuevo, stock=20, talla='L', color='Azul')
        self._agregar_variante(prod_nuevo, stock=15, talla='S', color='Rojo')

        # ESCENARIO 2 — Variante nueva en un producto que ya existía y ya
        # estaba 100% etiquetado (10 prendas nuevas)
        prod_viejo = self._crear_producto(f'{MARCA} Jean Existente', None, stock=8)
        v_vieja = prod_viejo.variantes.first()
        self._marcar_impresas(v_vieja, 8)  # el stock viejo ya tiene etiqueta
        v_nueva = self._agregar_variante(prod_viejo, stock=10, talla='XL', color='Gris')

        # ESCENARIO 3 — Aumento de stock en variante ya etiquetada:
        # tenía 10 impresas, llega mercadería y sube a 25 (15 prendas nuevas)
        prod_rest = self._crear_producto(f'{MARCA} Camiseta Reposición', None, stock=10)
        v_rest = prod_rest.variantes.first()
        self._marcar_impresas(v_rest, 10)
        self._ajustar_stock(v_rest, 25)

        # ESCENARIO 4 — Aumento de stock en variante con registro LEGACY
        # (impresa antes de que existiera stock_al_imprimir → quedó NULL).
        # Tenía 5 etiquetadas, sube a 10 (5 prendas nuevas).
        prod_leg = self._crear_producto(f'{MARCA} Blusa Legacy', None, stock=5)
        v_leg = prod_leg.variantes.first()
        EtiquetaImpresa.objects.create(
            codigo_barras=v_leg.codigo_barras,
            total_impresas=5,
            ultima_impresion=timezone.now(),
            stock_al_imprimir=None,  # así quedaron los registros pre-feature
        )
        self._ajustar_stock(v_leg, 10)

        # ESCENARIO 5 — Variante nueva con unidades apartadas (reservadas):
        # 5 prendas en percha, 2 apartadas por una clienta. Las 5 necesitan
        # etiqueta (la prenda apartada sigue en la tienda).
        prod_ap = self._crear_producto(f'{MARCA} Vestido Apartado', None, stock=5)
        v_ap = prod_ap.variantes.first()
        v_ap.stock_reservado = 2
        v_ap.save(update_fields=['stock_reservado'])

        # ── TOTAL ingresado que necesita etiqueta: 65+10+15+5+5 = 100 ──

        productos, impresas = self._estado_etiquetas()
        pendientes, total_etiquetas = _contar_etiquetas_pendientes(productos, impresas)

        por_codigo = {p['codigo_barras']: _faltantes(p, impresas) for p in productos}

        esperado = {
            'E1 variante 30': (prod_nuevo.variantes.get(talla='M').codigo_barras, 30),
            'E1 variante 20': (prod_nuevo.variantes.get(talla='L').codigo_barras, 20),
            'E1 variante 15': (prod_nuevo.variantes.get(talla='S').codigo_barras, 15),
            'E2 variante nueva en prod existente': (v_nueva.codigo_barras, 10),
            'E3 reposición de stock ya etiquetado': (v_rest.codigo_barras, 15),
            'E4 reposición sobre registro legacy': (v_leg.codigo_barras, 5),
            'E5 variante con apartados': (v_ap.codigo_barras, 5),
        }
        for nombre, (codigo, faltan_esperadas) in esperado.items():
            with self.subTest(escenario=nombre):
                self.assertEqual(
                    por_codigo.get(codigo), faltan_esperadas,
                    f'{nombre}: la pantalla daría {por_codigo.get(codigo)} '
                    f'etiquetas, deberían ser {faltan_esperadas}',
                )

        self.assertEqual(
            total_etiquetas, 100,
            f'Se ingresaron 100 prendas pero "Imprimir faltantes" daría '
            f'{total_etiquetas} etiquetas. Detalle: {por_codigo}',
        )

    # ── pruebas de los otros agujeros posibles ──

    def test_impresion_parcial_no_marca_todo_como_impreso(self):
        """Si el usuario imprime MENOS etiquetas que el stock (p. ej. cantidad
        fija 5 en vez de 'auto'), las unidades restantes deben seguir
        apareciendo como pendientes."""
        prod = self._crear_producto(f'{MARCA} Parcial', None, stock=10)
        v = prod.variantes.first()
        self._marcar_impresas(v, 5)  # imprimió solo 5 de 10

        productos, impresas = self._estado_etiquetas()
        p = next(x for x in productos if x['codigo_barras'] == v.codigo_barras)
        self.assertEqual(
            _faltantes(p, impresas), 5,
            'Imprimió 5 de 10 y el sistema dejó de contar las otras 5: '
            f'la pantalla daría {_faltantes(p, impresas)} faltantes',
        )

    def test_variante_sin_codigo_barras_no_desaparece(self):
        """Toda variante debe quedar con código de barras sin importar el
        flujo que la cree (el modelo lo garantiza); sin código, su stock es
        invisible en la pantalla de etiquetas. Las variantes viejas sin
        código las cubre la migración 0008."""
        v = Producto.objects.create(nombre=f'{MARCA} Sin Código', precio='9.99', stock=5)
        self.assertEqual(v.codigo_barras, f'TDA-{v.pk:06d}')

        productos, impresas = self._estado_etiquetas()
        pendientes, total = _contar_etiquetas_pendientes(productos, impresas)
        self.assertEqual(
            total, 5,
            'La variante sin código de barras desapareció del conteo '
            f'(la pantalla daría {total} etiquetas en vez de 5)',
        )

    def test_compra_a_proveedor_sobre_registro_legacy_cuenta_faltantes(self):
        """Recibir mercadería (compra a proveedor) sobre una variante cuyo
        registro de impresión es legacy (snapshot NULL) debe generar
        etiquetas faltantes por las unidades nuevas."""
        from apps.proveedores.models import Proveedor

        prod = self._crear_producto(f'{MARCA} Compra Legacy', None, stock=4)
        v = prod.variantes.first()
        EtiquetaImpresa.objects.create(
            codigo_barras=v.codigo_barras,
            total_impresas=4,
            ultima_impresion=timezone.now(),
            stock_al_imprimir=None,  # registro pre-feature
        )
        proveedor = Proveedor.objects.create(nombre=f'{MARCA} Proveedor')
        r = self.client.post(reverse('crear_compra'), {
            'proveedor_id': str(proveedor.pk),
            'fecha': '2026-06-11',
            'items_json': json.dumps([
                {'producto_id': v.pk, 'cantidad': 6, 'precio_unitario': '5.00'},
            ]),
        })
        self.assertEqual(r.status_code, 302, f'crear_compra falló: {r.status_code}')
        v.refresh_from_db()
        self.assertEqual(v.stock, 10)

        productos, impresas = self._estado_etiquetas()
        p = next(x for x in productos if x['codigo_barras'] == v.codigo_barras)
        self.assertEqual(
            _faltantes(p, impresas), 6,
            'Las 6 unidades recibidas en la compra no aparecen como '
            f'etiquetas faltantes (la pantalla daría {_faltantes(p, impresas)})',
        )

    def test_por_dia_de_ingreso_incluye_reposiciones_de_stock(self):
        """El filtro "Por día de ingreso" debe encontrar también las variantes
        que recibieron stock ese día (ajuste al alza o compra), no solo las
        creadas ese día."""
        from datetime import timedelta
        from apps.proveedores.models import Proveedor

        hoy = timezone.localdate().strftime('%Y-%m-%d')

        # Variante creada hace 10 días (la retro-fechamos)
        prod = self._crear_producto(f'{MARCA} Reposición Día', None, stock=5)
        v = prod.variantes.first()
        Producto.objects.filter(pk=v.pk).update(
            creado_en=timezone.now() - timedelta(days=10))

        def dato(codigo):
            productos, _ = self._estado_etiquetas()
            return next(x for x in productos if x['codigo_barras'] == codigo)

        # Bajar stock NO es un ingreso
        self._ajustar_stock(v, 3)
        p = dato(v.codigo_barras)
        self.assertEqual(p['ingreso'], '', 'Bajar stock no debe contar como ingreso')
        self.assertNotEqual(p['creado'], hoy)

        # Subir stock SÍ: la variante debe aparecer bajo el día de hoy
        self._ajustar_stock(v, 12)
        p = dato(v.codigo_barras)
        self.assertEqual(
            p['ingreso'], hoy,
            'La reposición por ajuste manual no quedó registrada como ingreso del día',
        )

        # También al recibir mercadería por compra a proveedor
        prod2 = self._crear_producto(f'{MARCA} Compra Día', None, stock=2)
        v2 = prod2.variantes.first()
        Producto.objects.filter(pk=v2.pk).update(
            creado_en=timezone.now() - timedelta(days=5), ultimo_ingreso_stock=None)
        proveedor = Proveedor.objects.create(nombre=f'{MARCA} Proveedor Día')
        r = self.client.post(reverse('crear_compra'), {
            'proveedor_id': str(proveedor.pk),
            'fecha': hoy,
            'items_json': json.dumps([
                {'producto_id': v2.pk, 'cantidad': 4, 'precio_unitario': '3.00'},
            ]),
        })
        self.assertEqual(r.status_code, 302)
        p2 = dato(v2.codigo_barras)
        self.assertEqual(
            p2['ingreso'], hoy,
            'La compra a proveedor no quedó registrada como ingreso del día',
        )

    def _buscar_inventario(self, q):
        """Nombres de catálogo que devuelve la búsqueda del inventario."""
        r = self.client.get(reverse('lista_inventario'), {'q': q})
        self.assertEqual(r.status_code, 200)
        return [c.nombre for c in r.context['catalogos']]

    def test_busqueda_inventario_por_similitud(self):
        """La búsqueda del inventario debe encontrar aunque falten acentos,
        las palabras vayan en otro orden o haya un error de tipeo leve —
        no solo cuando se escribe tal cual."""
        self._crear_producto(f'{MARCA} Paño bombacho con cierre', None, stock=1)
        self._crear_producto(f'{MARCA} Camiseata galleta de hombre', None, stock=1)
        self._crear_producto(f'{MARCA} Vestido corto de piedras', None, stock=1)

        casos = {
            'sin acentos':        ('pano bombacho', 'Paño bombacho con cierre'),
            'orden invertido':    ('bombacho paño', 'Paño bombacho con cierre'),
            'tipeo leve':         ('camiseta galeta', 'Camiseata galleta de hombre'),
            'palabras salteadas': ('vestido piedras', 'Vestido corto de piedras'),
            'literal':            ('Vestido corto', 'Vestido corto de piedras'),
        }
        for nombre_caso, (q, esperado) in casos.items():
            with self.subTest(caso=nombre_caso, q=q):
                nombres = self._buscar_inventario(q)
                self.assertTrue(
                    any(esperado in n for n in nombres),
                    f'Buscando "{q}" no apareció "{esperado}". Resultados: {nombres}',
                )

        # Y algo que no existe no debe traer resultados de relleno
        self.assertEqual(self._buscar_inventario('zapatilla deportiva runner'), [])

    def test_venta_de_prenda_nueva_descuenta_etiqueta_pendiente(self):
        """Si entran 10 prendas y se venden 2 antes de imprimir, deben quedar
        8 pendientes (las vendidas se fueron sin etiqueta, ya no la necesitan)."""
        prod = self._crear_producto(f'{MARCA} Vendida Antes', None, stock=10)
        v = prod.variantes.first()
        # La venta baja stock y descuenta el snapshot (igual que ventas/services)
        v.stock -= 2
        v.save(update_fields=['stock'])
        EtiquetaImpresa.descontar_por_venta(v.codigo_barras, 2)

        productos, impresas = self._estado_etiquetas()
        p = next(x for x in productos if x['codigo_barras'] == v.codigo_barras)
        self.assertEqual(_faltantes(p, impresas), 8)


@override_settings(STORAGES={
    'default':     {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
})
class BitacoraInventarioTest(TestCase):
    """La bitácora (MovimientoInventario) debe registrar cada cambio de stock
    con el antes/después correcto, y el campo Producto.stock_anterior debe
    reflejar el valor previo al último movimiento."""

    def setUp(self):
        self.user = Usuario.objects.create_user(
            username='test_bodeguero_log', password='x', rol=Usuario.ROL_DUENO,
        )
        self.client.force_login(self.user)

    def _movs(self, producto, tipo=None):
        qs = MovimientoInventario.objects.filter(producto=producto)
        if tipo:
            qs = qs.filter(tipo=tipo)
        return list(qs.order_by('creado_en', 'id'))

    def test_creacion_de_producto_y_variante_se_registran(self):
        r = self.client.post(reverse('crear_producto'), {
            'nombre': f'{MARCA} Bitácora', 'categoria': '',
            'precio_minimo': '10.00', 'precio_maximo': '15.00',
            'color': 'Negro', 'talla': 'M', 'stock': '7',
        })
        self.assertEqual(r.status_code, 302)
        catalogo = CatalogoProducto.objects.get(nombre=f'{MARCA} Bitácora')
        v = catalogo.variantes.first()
        movs = self._movs(v, MovimientoInventario.CREACION)
        self.assertEqual(len(movs), 1)
        self.assertEqual((movs[0].stock_anterior, movs[0].stock_nuevo), (0, 7))
        self.assertEqual(movs[0].usuario, self.user)

        # Agregar variante también se registra
        r = self.client.post(reverse('agregar_variante', args=[catalogo.pk]), {
            'color': 'Azul', 'talla': 'L', 'precio': '12.00', 'stock': '3',
        })
        self.assertEqual(r.status_code, 302)
        v2 = catalogo.variantes.get(talla='L')
        movs2 = self._movs(v2, MovimientoInventario.CREACION)
        self.assertEqual(len(movs2), 1)
        self.assertEqual(movs2[0].stock_nuevo, 3)

    def test_ajuste_de_stock_registra_antes_y_despues(self):
        r = self.client.post(reverse('crear_producto'), {
            'nombre': f'{MARCA} Ajuste', 'categoria': '',
            'precio_minimo': '10.00', 'precio_maximo': '15.00',
            'color': 'Gris', 'talla': 'M', 'stock': '5',
        })
        v = CatalogoProducto.objects.get(nombre=f'{MARCA} Ajuste').variantes.first()

        # Subir 5 → 12
        self.client.post(reverse('ajustar_stock', args=[v.pk]), {'stock': '12'})
        # Bajar 12 → 8
        self.client.post(reverse('ajustar_stock', args=[v.pk]), {'stock': '8'})

        ajustes = self._movs(v, MovimientoInventario.AJUSTE)
        self.assertEqual(len(ajustes), 2)
        self.assertEqual((ajustes[0].stock_anterior, ajustes[0].stock_nuevo), (5, 12))
        self.assertEqual((ajustes[1].stock_anterior, ajustes[1].stock_nuevo), (12, 8))

        # El campo de la pantalla refleja el valor previo al último cambio
        v.refresh_from_db()
        self.assertEqual(v.stock_anterior, 12)
        self.assertEqual(v.stock, 8)

    def test_ajuste_sin_cambio_no_genera_movimiento(self):
        v = CatalogoProducto.objects.create(
            nombre=f'{MARCA} SinCambio', precio_base=10).variantes.create(
            nombre='x', precio=10, stock=5)
        self.client.post(reverse('ajustar_stock', args=[v.pk]), {'stock': '5'})
        self.assertEqual(self._movs(v, MovimientoInventario.AJUSTE), [])

    def test_venta_contado_registra_movimiento(self):
        from apps.ventas.services import crear_venta_contado
        from apps.configuracion.models import ConfiguracionGeneral

        cat = CatalogoProducto.objects.create(nombre=f'{MARCA} Venta', precio_base=10)
        v = cat.variantes.create(nombre=f'{MARCA} Venta', precio=10, stock=10)

        crear_venta_contado(
            items=[{'producto_id': v.pk, 'cantidad': 3, 'precio_unitario': '10.00'}],
            cliente_id=None, vendedor=self.user, forma_pago='efectivo',
            cfg_gen=ConfiguracionGeneral.get_singleton(),
        )
        ventas = self._movs(v, MovimientoInventario.VENTA)
        self.assertEqual(len(ventas), 1)
        self.assertEqual((ventas[0].stock_anterior, ventas[0].stock_nuevo), (10, 7))
        self.assertTrue(ventas[0].referencia.startswith('Venta #'))

    def test_compra_a_proveedor_registra_movimiento(self):
        from apps.proveedores.models import Proveedor

        cat = CatalogoProducto.objects.create(nombre=f'{MARCA} CompraLog', precio_base=10)
        v = cat.variantes.create(nombre=f'{MARCA} CompraLog', precio=10, stock=4)
        proveedor = Proveedor.objects.create(nombre=f'{MARCA} Prov')
        r = self.client.post(reverse('crear_compra'), {
            'proveedor_id': str(proveedor.pk), 'fecha': '2026-06-12',
            'items_json': json.dumps([
                {'producto_id': v.pk, 'cantidad': 6, 'precio_unitario': '5.00'},
            ]),
        })
        self.assertEqual(r.status_code, 302)
        compras = self._movs(v, MovimientoInventario.COMPRA)
        self.assertEqual(len(compras), 1)
        self.assertEqual((compras[0].stock_anterior, compras[0].stock_nuevo), (4, 10))

    def test_reporte_historial_carga_y_filtra(self):
        cat = CatalogoProducto.objects.create(nombre=f'{MARCA} Reporte', precio_base=10)
        v = cat.variantes.create(nombre=f'{MARCA} Reporte ABC', precio=10, stock=2)
        self.client.post(reverse('ajustar_stock', args=[v.pk]), {'stock': '9'})

        r = self.client.get(reverse('historial_inventario'))
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.context['total'], 1)

        # Filtro por tipo
        r = self.client.get(reverse('historial_inventario'), {'tipo': MovimientoInventario.AJUSTE})
        self.assertTrue(all(m.tipo == MovimientoInventario.AJUSTE for m in r.context['movimientos']))

        # Filtro por texto (código de barras)
        r = self.client.get(reverse('historial_inventario'), {'q': v.codigo_barras})
        self.assertTrue(all(v.codigo_barras == m.codigo_barras for m in r.context['movimientos']))
        self.assertGreaterEqual(r.context['total'], 1)

    def test_api_ingreso_dia_devuelve_solo_lo_ingresado(self):
        """El endpoint de 'por día de ingreso' debe devolver las unidades que
        ENTRARON ese día (deltas positivos), no el stock total. Una variante
        repuesta de 21 a 22 debe dar 1, no 22."""
        from apps.inventario.services import registrar_movimiento

        cat = CatalogoProducto.objects.create(nombre=f'{MARCA} IngresoDia', precio_base=10)
        # Repuesta hoy +1 (de 21 a 22): debe contar 1
        v1 = cat.variantes.create(nombre=f'{MARCA} v1', precio=10, stock=22)
        registrar_movimiento(v1, MovimientoInventario.AJUSTE, stock_anterior=21, stock_nuevo=22, usuario=self.user)
        # Creada hoy con 3: debe contar 3
        v2 = cat.variantes.create(nombre=f'{MARCA} v2', precio=10, stock=3)
        registrar_movimiento(v2, MovimientoInventario.CREACION, stock_anterior=0, stock_nuevo=3, usuario=self.user)
        # Una venta el mismo día NO cuenta como ingreso
        registrar_movimiento(v1, MovimientoInventario.VENTA, stock_anterior=22, stock_nuevo=20, usuario=self.user)

        from django.utils import timezone
        hoy = timezone.localdate().strftime('%Y-%m-%d')
        r = self.client.get(reverse('api_etiquetas_ingreso_dia'), {'fecha': hoy})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['por_codigo'].get(v1.codigo_barras), 1)   # +1, NO 22
        self.assertEqual(data['por_codigo'].get(v2.codigo_barras), 3)
        self.assertEqual(data['total_unidades'], 4)

    def test_filtro_por_varios_tipos_a_la_vez(self):
        from apps.inventario.services import registrar_movimiento
        cat = CatalogoProducto.objects.create(nombre=f'{MARCA} Multi', precio_base=10)
        v = cat.variantes.create(nombre=f'{MARCA} Multi', precio=10, stock=5)
        registrar_movimiento(v, MovimientoInventario.AJUSTE, stock_anterior=5, stock_nuevo=8, usuario=self.user)
        registrar_movimiento(v, MovimientoInventario.COMPRA, stock_anterior=8, stock_nuevo=12, usuario=self.user)
        registrar_movimiento(v, MovimientoInventario.VENTA, stock_anterior=12, stock_nuevo=10, usuario=self.user)

        # Marcar dos tipos a la vez (?tipo=ajuste&tipo=compra)
        r = self.client.get(reverse('historial_inventario'),
                            {'tipo': [MovimientoInventario.AJUSTE, MovimientoInventario.COMPRA]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total'], 2)
        tipos_result = {m.tipo for m in r.context['movimientos']}
        self.assertEqual(tipos_result, {MovimientoInventario.AJUSTE, MovimientoInventario.COMPRA})
        # Y el contexto refleja ambos como seleccionados (para marcar las casillas)
        self.assertEqual(set(r.context['f_tipos']),
                         {MovimientoInventario.AJUSTE, MovimientoInventario.COMPRA})
