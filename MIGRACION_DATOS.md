# Migración de datos — desde Excel o cuaderno

Esta guía describe cómo cargar los datos existentes (clientes, productos, deudas activas, adelantos activos) al sistema antes de arrancar en producción.

---

## Orden recomendado

1. Clientes
2. Productos (inventario)
3. Adelantos activos
4. Deudas activas

No cargues ventas históricas en el primer arranque — solo lo que está **pendiente** hoy.

---

## Opción A: Admin de Django (recomendado para pocas filas)

Accede a `https://tu-sitio.railway.app/admin/` con el usuario dueño.

### Clientes
1. **Clientes → Agregar cliente**
2. Campos: Nombre, Cédula/RUC, Teléfono, Email (opcional), Dirección (opcional)
3. Si el cliente tiene **crédito a favor** de un apartado cancelado, ingresa el valor en "Saldo a favor"

### Productos
1. **Inventario → Agregar producto**
2. Campos: Nombre, Talla, Color, Precio, Stock actual
3. Stock reservado: déjalo en 0 — se actualizará al cargar los adelantos

### Adelantos activos
Para cada apartado activo que existe en el cuaderno:
1. **Deudores → Adelantos → Agregar adelanto**
2. Campos: Cliente, Total, Saldo pendiente (lo que falta cobrar), Estado = Activo, Fecha límite (si la tiene)
3. Agrega los ítems del apartado (producto, cantidad, precio unitario)
4. **Importante**: actualiza manualmente el `stock_reservado` del producto correspondiente en Inventario

### Deudas activas
Para cada venta a crédito pendiente:
1. **Deudores → Deudas → Agregar deuda**
2. Campos: Cliente, Monto original, Saldo pendiente, Estado = Pendiente, Fecha vencimiento
3. El campo "Venta" puede dejarse vacío en la migración inicial

---

## Opción B: Script de importación desde CSV (para muchos registros)

Si tienes los datos en Excel, expórtalos como CSV y usa el siguiente script de gestión de Django.

### Formato CSV de clientes (`clientes.csv`)
```
nombre,cedula_ruc,telefono,saldo_a_favor
Ana Torres,1710034065,0987654321,0.00
Pedro Mora,0102030405,0991234567,15.00
```

### Script de importación

Crea el archivo `scripts/importar_datos.py` en el proyecto:

```python
import csv
from decimal import Decimal
from apps.clientes.models import Cliente

def importar_clientes(ruta_csv):
    with open(ruta_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            Cliente.objects.get_or_create(
                cedula_ruc=row['cedula_ruc'],
                defaults={
                    'nombre': row['nombre'],
                    'telefono': row.get('telefono', ''),
                    'saldo_a_favor': Decimal(row.get('saldo_a_favor', '0')),
                }
            )
    print("Clientes importados.")
```

Ejecuta desde el shell de Railway:
```bash
python manage.py shell
>>> exec(open('scripts/importar_datos.py').read())
>>> importar_clientes('clientes.csv')
```

---

## Verificación post-migración

Antes de arrancar con operaciones reales, verifica:

- [ ] El total de clientes en el sistema coincide con el cuaderno
- [ ] El stock de cada producto es correcto (stock físico − stock de apartados activos = stock disponible)
- [ ] Cada adelanto activo tiene su saldo pendiente correcto
- [ ] Cada deuda activa tiene su saldo pendiente correcto
- [ ] El dashboard muestra los totales correctos

---

## Nota sobre cédulas/RUC

El sistema valida el dígito verificador de cédulas y RUC ecuatorianos (algoritmo Módulo 11 del SRI). Si tienes clientes sin cédula o con número incorrecto, ingresa un valor temporal como `9999999999` y actualiza luego cuando tengas el documento.
