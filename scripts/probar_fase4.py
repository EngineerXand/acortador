"""Demuestra el failover de Redis (Fase 4). Solo librería estándar.

    python scripts/probar_fase4.py [segundos=60] [url=http://localhost:8001]

Acorta una URL cada 0.2 s durante N segundos y avisa cada vez que el servicio
falla o se recupera. Mientras corre, en OTRA terminal tumben el maestro:

    docker stop acortador-redis-master-1

Al final verifica que cada enlace confirmado (201) siga existiendo y apunte a
la URL correcta, y reporta cuánto duró la caída.
"""
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SEGUNDOS = int(sys.argv[1]) if len(sys.argv) > 1 else 60
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8001"


def llamar(ruta, cuerpo=None):
    """Devuelve (status, json). status=0 si ni siquiera hubo respuesta."""
    req = Request(BASE + ruta, json.dumps(cuerpo).encode() if cuerpo else None,
                  {"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=3) as r:
            return r.status, json.load(r)
    except HTTPError as e:
        return e.code, {}
    except (URLError, OSError):
        return 0, {}


def esperar_servicio():
    while llamar("/health")[0] != 200:
        print("Esperando a que el servicio esté listo...")
        time.sleep(2)


esperar_servicio()
print(f"Acortando durante {SEGUNDOS} s. Tumben el maestro en otra terminal:")
print("    docker stop acortador-redis-master-1\n")

guardados = {}  # codigo -> url que enviamos
ok, fallos, caidas = 0, 0, []
inicio, caida_desde, i = time.time(), None, 0

while time.time() - inicio < SEGUNDOS:
    i += 1
    url = f"https://ejemplo.com/pagina/{i}"
    status, datos = llamar("/shorten", {"url": url})
    t = time.time() - inicio
    if status == 201:
        guardados[datos["codigo"]] = url
        ok += 1
        if caida_desde is not None:
            caidas.append(t - caida_desde)
            print(f"[{t:5.1f}s] Servicio RECUPERADO tras {t - caida_desde:.1f} s de caída")
            caida_desde = None
    else:
        fallos += 1
        if caida_desde is None:
            caida_desde = t
            print(f"[{t:5.1f}s] FALLO (HTTP {status or 'sin respuesta'}): el servicio no puede escribir")
    time.sleep(0.2)

print(f"\nAcortados con éxito: {ok}   Fallidos: {fallos}")
for n, d in enumerate(caidas, 1):
    print(f"Caída {n}: {d:.1f} s sin poder escribir")

print("Verificando enlaces confirmados...")
perdidos, cambiados = [], []
for codigo, url in guardados.items():
    for _ in range(10):  # reintenta por si aún hay un 503 residual
        status, datos = llamar(f"/stats/{codigo}")
        if status in (200, 404):
            break
        time.sleep(1)
    if status == 404:
        perdidos.append(codigo)
    elif status == 200 and datos["url"] != url:
        cambiados.append(codigo)

print(f"Perdidos (confirmados pero ya no existen): {len(perdidos)} {perdidos[:5]}")
print(f"Pisados (el código ahora apunta a otra URL): {len(cambiados)} {cambiados[:5]}")
print("OK: sin pérdida de datos." if not perdidos and not cambiados
      else "Hubo pérdida: es la consecuencia de la replicación asíncrona (ver README).")
