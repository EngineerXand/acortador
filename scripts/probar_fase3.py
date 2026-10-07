"""Demuestra la Fase 3. Solo usa la librería estándar:  python scripts/probar_fase3.py

1. Reparto: 30 peticiones a /health -> cuántas atendió cada réplica.
2. Unicidad: 200 acortados en paralelo -> ningún código repetido.
"""
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"


def get_json(ruta):
    with urlopen(BASE + ruta) as r:
        return json.load(r)


def acortar(i):
    body = json.dumps({"url": f"https://ejemplo.com/pagina/{i}"}).encode()
    req = Request(BASE + "/shorten", body, {"Content-Type": "application/json"})
    with urlopen(req) as r:
        return json.load(r)["codigo"]


reparto = Counter(get_json("/health")["instancia"] for _ in range(30))
print("Reparto de 30 peticiones:", dict(reparto))

with ThreadPoolExecutor(max_workers=20) as pool:
    codigos = list(pool.map(acortar, range(200)))

print(f"Códigos generados: {len(codigos)}, únicos: {len(set(codigos))}")
assert len(set(codigos)) == len(codigos), "¡Hay códigos repetidos!"
assert len(reparto) > 1, "Todas las peticiones fueron a una sola réplica"
print("OK: carga repartida y sin colisiones de IDs.")
