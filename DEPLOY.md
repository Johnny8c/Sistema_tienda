# Despliegue en Railway

## Requisitos previos
- Cuenta en [railway.app](https://railway.app)
- Git instalado
- Python 3.12+ en local para pruebas

---

## 1. Crear proyecto en Railway

1. Ingresa a railway.app → **New Project** → **Deploy from GitHub repo**
2. Conecta tu cuenta de GitHub y selecciona el repositorio `Sistema_tienda`
3. Railway detecta automáticamente que es una app Python/Django

---

## 2. Agregar base de datos PostgreSQL

1. En el proyecto Railway → **+ New** → **Database** → **PostgreSQL**
2. Railway crea la base automáticamente y expone la variable `DATABASE_URL`

---

## 3. Variables de entorno

En el servicio web (no en la base de datos), ve a **Variables** y agrega:

| Variable | Valor |
|---|---|
| `SECRET_KEY` | Genera una con: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | `*.railway.app` (Railway lo completa automáticamente) |
| `DATABASE_URL` | Railway lo inyecta solo desde el servicio PostgreSQL |

> **Nota:** `DATABASE_URL` se copia desde el servicio PostgreSQL → pestaña **Connect** → *Database URL*. Si Railway los enlaza en el mismo proyecto, se inyecta automáticamente.

---

## 4. Archivo `Procfile`

El repositorio ya incluye `Procfile` con:
```
web: gunicorn core.wsgi --bind 0.0.0.0:$PORT
```

---

## 5. Migraciones y superusuario (primer despliegue)

Una vez desplegada la app, abre la terminal de Railway (**Shell** en el servicio):

```bash
python manage.py migrate
python manage.py createsuperuser
```

El superusuario creado tendrá `rol = dueno` por defecto si usas el shell interactivo; o bien crea el usuario desde el admin (`/admin/`) y cambia el rol a `dueno`.

---

## 6. Archivos estáticos

Whitenoise sirve los estáticos automáticamente. Si necesitas recolectarlos manualmente:

```bash
python manage.py collectstatic --noinput
```

Railway ejecuta esto si lo agregas como comando de build en **Settings → Build Command**:
```
python manage.py collectstatic --noinput
```

---

## 7. Verificar despliegue

1. Railway asigna una URL tipo `https://sistema-tienda-production.up.railway.app`
2. Accede a `/admin/` para confirmar que el admin de Django carga
3. Inicia sesión con el superusuario creado
4. Accede al dashboard y verifica que todas las secciones cargan

---

## 8. Crear usuarios

Desde `/admin/usuarios/usuario/` crea los usuarios para el dueño, vendedores y bodegueros con sus respectivos roles.

---

## Costos estimados

| Recurso | Costo mensual |
|---|---|
| App web (512 MB RAM) | ~$5 USD |
| PostgreSQL (1 GB) | incluido en el plan Hobby |
| **Total** | **~$5 USD/mes** |

El plan Hobby de Railway incluye $5 de crédito mensual, por lo que el primer mes puede ser gratuito.
