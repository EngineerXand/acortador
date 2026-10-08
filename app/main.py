"""API del acortador de URLs — Fase 1 (una instancia + Redis).

Endpoints:
    POST /shorten          crea un enlace corto
    GET  /{codigo}         redirige a la URL original
    GET  /stats/{codigo}   muestra clics y fecha de creación
    GET  /health           indica si el servicio y Redis están vivos
"""

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
import redis
from pydantic import BaseModel, HttpUrl

from . import config
from .storage import Almacen, crear_cliente

app = FastAPI(
    title="Acortador de URLs",
    description="Proyecto de Sistemas Distribuidos — Fase 1",
    version="1.0.0",
)

_almacen: Almacen | None = None


def obtener_almacen() -> Almacen:
    """Dependencia de FastAPI: entrega la conexión a Redis.

    Las pruebas la reemplazan por un Redis falso en memoria.
    """
    global _almacen
    if _almacen is None:
        _almacen = Almacen(crear_cliente())
    return _almacen


@app.exception_handler(redis.RedisError)
def almacen_no_disponible(request, exc):
    # Durante un failover (unos segundos) Redis no responde: en vez de un
    # 500 confuso, avisamos "temporalmente no disponible, reintente".
    return JSONResponse(
        {"detail": "Almacenamiento no disponible, reintente"},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        headers={"Retry-After": "2"},
    )


# ---------- Modelos de entrada y salida ----------

class PeticionAcortar(BaseModel):
    # HttpUrl valida que sea una URL real (http/https); si no, responde 422.
    url: HttpUrl


class RespuestaAcortar(BaseModel):
    codigo: str
    short_url: str
    url_original: str


class Estadisticas(BaseModel):
    codigo: str
    url: str
    creado: str
    clics: int


# ---------- Endpoints ----------

@app.get("/health")
def salud(almacen: Almacen = Depends(obtener_almacen)):
    redis_ok = almacen.esta_vivo()
    if not redis_ok:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis no responde")
    return {"estado": "ok", "redis": "ok", "instancia": config.INSTANCIA}


@app.post("/shorten", response_model=RespuestaAcortar, status_code=status.HTTP_201_CREATED)
def acortar(peticion: PeticionAcortar, almacen: Almacen = Depends(obtener_almacen)):
    url = str(peticion.url)
    codigo = almacen.guardar(url)
    return RespuestaAcortar(
        codigo=codigo,
        short_url=f"{config.BASE_URL}/{codigo}",
        url_original=url,
    )


@app.get("/stats/{codigo}", response_model=Estadisticas)
def estadisticas(codigo: str, almacen: Almacen = Depends(obtener_almacen)):
    datos = almacen.estadisticas(codigo)
    if datos is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El enlace no existe")
    return Estadisticas(codigo=codigo, **datos)


# Esta ruta va al final porque /{codigo} atrapa cualquier ruta de un nivel.
@app.get("/{codigo}")
def redirigir(codigo: str, almacen: Almacen = Depends(obtener_almacen)):
    url = almacen.obtener_url(codigo)
    if url is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El enlace no existe")
    # 302 (temporal) en vez de 301 (permanente): con 301 el navegador
    # guarda la redirección y ya no vuelve a pasar por nosotros,
    # así que no podríamos contar los clics.
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)
