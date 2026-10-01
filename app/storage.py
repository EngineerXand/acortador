"""Capa de almacenamiento en Redis.

Toda la lógica de datos vive aquí, separada de la API. Así en fases
posteriores podemos cambiar cómo se guarda (réplicas, sharding, caché)
sin tocar los endpoints.

Estructura de claves en Redis:
    contador:urls        -> entero que se incrementa con cada enlace nuevo
    url:{codigo}         -> hash con {url, creado, clics}
"""

from datetime import datetime, timezone

import redis

from . import base62, config

CLAVE_CONTADOR = "contador:urls"


def clave_url(codigo: str) -> str:
    return f"url:{codigo}"


class Almacen:
    def __init__(self, cliente: redis.Redis):
        self.r = cliente

    def siguiente_id(self) -> int:
        """Genera un ID único.

        INCR en Redis es atómico: aunque dos peticiones lleguen al mismo
        tiempo, cada una recibe un número distinto. Por eso sirve como
        generador de IDs mientras haya un solo Redis (en la Fase 3
        veremos qué pasa cuando hay varios).
        """
        # Inicializa el contador la primera vez (NX = solo si no existe).
        self.r.set(CLAVE_CONTADOR, config.CONTADOR_INICIAL, nx=True)
        return self.r.incr(CLAVE_CONTADOR)

    def guardar(self, url: str) -> str:
        codigo = base62.codificar(self.siguiente_id())
        self.r.hset(
            clave_url(codigo),
            mapping={
                "url": url,
                "creado": datetime.now(timezone.utc).isoformat(),
                "clics": 0,
            },
        )
        return codigo

    def obtener_url(self, codigo: str) -> str | None:
        """Devuelve la URL original y suma un clic. None si no existe."""
        url = self.r.hget(clave_url(codigo), "url")
        if url is not None:
            self.r.hincrby(clave_url(codigo), "clics", 1)
        return url

    def estadisticas(self, codigo: str) -> dict | None:
        datos = self.r.hgetall(clave_url(codigo))
        if not datos:
            return None
        datos["clics"] = int(datos["clics"])
        return datos

    def esta_vivo(self) -> bool:
        try:
            return bool(self.r.ping())
        except redis.RedisError:
            return False


def crear_cliente() -> redis.Redis:
    return redis.Redis(
        host=config.REDIS_HOST,
        port=config.REDIS_PORT,
        decode_responses=True,  # devuelve str en lugar de bytes
    )
