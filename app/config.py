"""Configuración leída desde variables de entorno (las define docker-compose)."""

import os

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Si REDIS_SENTINELS está definido ("host1:26379,host2:26379,..."), la API le
# pregunta a Sentinel quién es el maestro actual (Fase 4). Si no, usa
# REDIS_HOST directamente (desarrollo local y pruebas).
REDIS_SENTINELS = os.getenv("REDIS_SENTINELS", "")
REDIS_MASTER = os.getenv("REDIS_MASTER", "mymaster")

# Dominio que se antepone al código corto en las respuestas.
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

# El contador arranca en este valor para que los primeros códigos
# no sean de 1 solo carácter (100000 en Base62 = 'q0U').
CONTADOR_INICIAL = int(os.getenv("CONTADOR_INICIAL", "100000"))

# Identificador de esta instancia. En la Fase 3 habrá varias y
# nos servirá para ver cuál atendió cada petición.
INSTANCIA = os.getenv("HOSTNAME", "local")
