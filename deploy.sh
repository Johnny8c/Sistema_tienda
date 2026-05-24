#!/bin/bash
# Script de despliegue Sistema_tienda — SERVIDOR (EC2)
# Ejecutar en el servidor: bash deploy.sh
# Mismo patrón que el deploy.sh de systemdent.
set -e

echo "=== Sistema_tienda Deploy ==="

# 1. Traer última versión del repo
git pull origin main

# 2. Rebuild y reiniciar el contenedor Django
echo ">> Restarting Django container..."
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d

# 3. Recargar nginx
sudo nginx -t && sudo systemctl reload nginx

echo "=== Deploy completado ==="
echo "Logs en vivo:  docker-compose -f docker-compose.prod.yml logs -f web"
