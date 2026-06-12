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
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Categoria, CatalogoProducto, Producto, EtiquetaImpresa

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
