# Dockerfile para Sistema_tienda (Django + gunicorn)
# Patron equivalente al de systemdent: contenedor expuesto solo en
# 127.0.0.1, nginx en el host como reverse proxy.

FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Dependencias del sistema:
#  - libpq-dev: necesario para psycopg2-binary al conectar a Postgres
#  - tzdata: zona horaria America/Guayaquil
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq-dev \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Guayaquil

# Requirements primero (mejor cacheado)
COPY requirements.txt .
RUN pip install -r requirements.txt

# Código de la app
COPY . .

# Recolectar staticos al BUILD (WhiteNoise los sirve dentro de gunicorn).
# DEBUG=True en build para que no se exijan settings de producción.
RUN DEBUG=True python manage.py collectstatic --noinput

EXPOSE 8000

# Migraciones al arrancar + gunicorn.
# 2 workers es seguro en t3.micro. Subí si la CPU sobra y el RAM aguanta.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn core.wsgi --bind 0.0.0.0:8000 --workers 2 --timeout 60 --log-file - --access-logfile -"]
