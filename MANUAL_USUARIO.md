# Manual de Usuario — Sistema Tienda

## Roles del sistema

| Rol | Qué puede hacer |
|---|---|
| **Dueño** | Todo: ventas, adelantos, deudas, reportes, cierre de caja, cancelar/condonar |
| **Vendedor** | Ventas, adelantos, deudas (abonar), clientes |
| **Bodeguero** | Solo ve el inventario y el dashboard básico |

---

## Para el dueño

### Cierre de caja
1. Sidebar → **Cierre de caja**
2. Selecciona la fecha y haz clic en **Ver**
3. Verás el resumen del día: ventas al contado, abonos a adelantos y abonos a deudas
4. El total de ingresos aparece en verde arriba a la derecha

### Reportes
1. Sidebar → **Reportes**
2. Tres secciones disponibles:
   - **Antigüedad de cartera**: deudas agrupadas por 0-30, 31-60, 61-90 y más de 90 días
   - **Adelantos por vencer**: apartados vencidos, próximos a vencer (7 días) y sin fecha
   - **Top deudores**: clientes con mayor saldo pendiente

### Cancelar un apartado
Solo el dueño puede cancelar. El dinero pagado queda como **crédito a favor** del cliente.
1. Sidebar → **Adelantos** → busca el apartado
2. Abre el detalle y haz clic en **Cancelar**
3. Ingresa el motivo → el stock se libera automáticamente

### Condonar una deuda
Solo el dueño puede condonar (perdonar) una deuda.
1. Sidebar → **Deudores** → busca la deuda
2. Abre el detalle y haz clic en **Condonar**
3. Ingresa el motivo → la deuda queda marcada como condonada

---

## Para el vendedor

### Punto de venta (POS)
1. Sidebar → **Punto de venta**
2. Busca productos por nombre, talla o color
3. Agrega al carrito con la cantidad
4. Selecciona **Contado** o **Crédito**
   - **Contado**: descuenta stock inmediatamente, registra la venta
   - **Crédito**: descuenta stock, crea una deuda a nombre del cliente con plazo de días

### Crear un apartado (adelanto)
1. Sidebar → **Adelantos** → **Nuevo apartado**
2. Selecciona el cliente (o créalo en el momento)
3. Agrega los productos y cantidades
4. Ingresa el monto inicial (puede ser $0 si no paga nada hoy)
5. Opcionalmente, ingresa una fecha límite
6. El stock queda **reservado** (no descontado hasta completar)

### Abonar a un apartado
1. Sidebar → **Adelantos** → busca el apartado activo
2. Haz clic en **Abonar**
3. Ingresa el monto y la forma de pago (efectivo / tarjeta / transferencia)

### Completar un apartado
Solo cuando el saldo pendiente es **$0.00**.
1. En el detalle del apartado → **Completar**
2. El stock se descuenta definitivamente y se genera la venta

### Registrar abono a una deuda
1. Sidebar → **Deudores** → busca la deuda pendiente
2. Haz clic en **Abonar**
3. Ingresa el monto y la forma de pago

---

## Para el bodeguero

### Ver inventario
1. Sidebar → **Inventario**
2. Puedes ver el stock disponible y el stock reservado de cada producto

> El bodeguero **no** tiene acceso a ventas, adelantos, deudas ni reportes.

---

## Preguntas frecuentes

**¿Qué pasa si un cliente cancela su apartado?**
El dinero que pagó queda como crédito a su favor. La próxima vez que compre, el vendedor puede aplicar ese crédito.

**¿Se puede abonar en partes a una deuda?**
Sí. Puedes hacer tantos abonos parciales como quieras. La deuda se marca como "Saldada" automáticamente cuando el saldo llega a $0.

**¿El sistema avisa cuando un apartado está por vencer?**
Sí. En el Dashboard aparece la tabla "Apartados vencidos" con los que ya pasaron su fecha límite.

**¿Cómo agrego un nuevo producto?**
Solo el dueño puede agregar productos desde la sección Inventario.
